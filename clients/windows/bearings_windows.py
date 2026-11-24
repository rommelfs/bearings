# SPDX-License-Identifier: AGPL-3.0-or-later
"""Windows machine inventory, outbound signed observations; no remote execution."""

import argparse
import base64
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import platform
import re
import ssl
import sys
import tempfile
import time
from urllib.parse import urlsplit
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

MAX_BODY = 1_000_000
TAG = "bearings.agent.v1"
UNINSTALL = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
OS_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"


def packed(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode()


def clean(value, maximum, allow_empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not value and not allow_empty):
        raise ValueError("Inventory field missing or exceeds contract")
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Inventory field contains control characters")
    return value


def component(key, name, version, arch, evidence):
    return dict(
        key=key,
        manager="win-reg",
        name=clean(name, 128),
        version=clean(version, 120, True),
        architecture=arch,
        windows=evidence,
    )


def collect(reg=None):
    if reg is None:
        import winreg as reg
    arch = {"amd64": "x86_64", "arm64": "arm64", "x86": "x86"}.get(platform.machine().lower())
    if arch is None:
        raise ValueError("Unsupported Windows architecture")
    access = reg.KEY_READ | reg.KEY_WOW64_64KEY
    with reg.OpenKey(reg.HKEY_LOCAL_MACHINE, OS_KEY, 0, access) as key:

        def value(name, default=None):
            try:
                return reg.QueryValueEx(key, name)[0]
            except FileNotFoundError:
                if default is None:
                    raise
                return default

        name = value("ProductName")
        edition = value("EditionID", "")
        release = value("DisplayVersion", "")
        build, revision = value("CurrentBuildNumber"), value("UBR")
        if not isinstance(build, str) or not build.isdigit() or type(revision) is not int or revision < 0:
            raise ValueError("Windows build/UBR unavailable")
        build = build + "." + str(revision)
    os_data = dict(
        id="windows",
        version=build,
        architecture=arch,
        kernel=build,
        kernel_scope="host",
        reboot_hint="unknown",
    )
    components = [
        component(
            "win-reg:os:all",
            name,
            build,
            "all",
            dict(
                kind="os",
                registry_key=OS_KEY,
                view="native",
                publisher="Microsoft",
                edition=clean(edition, 120, True),
                release=clean(release, 120, True),
            ),
        )
    ]
    # Registry views identify registration locations, not executable architecture.
    for view, flag in (("64", reg.KEY_WOW64_64KEY), ("32", reg.KEY_WOW64_32KEY)):
        if arch == "x86" and view == "64":
            continue
        try:
            root = reg.OpenKey(reg.HKEY_LOCAL_MACHINE, UNINSTALL, 0, reg.KEY_READ | flag)
        except FileNotFoundError:
            continue  # An absent uninstall database is a valid empty scope.
        with root as root:
            count = reg.QueryInfoKey(root)[0]
            if count > 5000:
                raise ValueError("Registry inventory exceeds 5000 entries")
            for index in range(count):
                subkey = reg.EnumKey(root, index)
                path = UNINSTALL + "\\" + subkey
                with reg.OpenKey(reg.HKEY_LOCAL_MACHINE, path, 0, reg.KEY_READ | flag) as key:

                    def optional(field):
                        try:
                            return reg.QueryValueEx(key, field)[0]
                        except FileNotFoundError:
                            return ""

                    name = optional("DisplayName")
                    if not name:
                        continue
                    version = optional("DisplayVersion")
                    publisher = clean(optional("Publisher"), 255, True)
                    clean(path, 1024)
                    identity = hashlib.sha256((view + ":" + path.casefold()).encode()).hexdigest()
                    components.append(
                        component(
                            "win-reg:" + identity + ":all",
                            name,
                            version,
                            "all",
                            dict(
                                kind="program",
                                registry_key=path,
                                view=view,
                                publisher=publisher,
                                edition="",
                                release="",
                            ),
                        )
                    )
                    if len(components) > 5000:
                        raise ValueError("Inventory exceeds 5000 components; nothing sent")
    result = dict(
        schema=TAG,
        report_id=str(uuid.uuid4()),
        sequence=1,
        observed_at=datetime.now(timezone.utc).isoformat(),
        scope="windows-machine",
        complete=True,
        os=os_data,
        components=sorted(components, key=lambda c: c["key"]),
        services=[],
    )
    if len(packed(result)) > MAX_BODY:
        raise ValueError("Inventory exceeds one megabyte; nothing sent")
    return result


def origin(value):
    u = urlsplit(value)
    if (
        u.scheme != "https"
        or not u.hostname
        or u.username
        or u.password
        or u.path not in ("", "/")
        or u.query
        or u.fragment
        or any(c.isspace() for c in value)
    ):
        raise ValueError("Use a trusted HTTPS origin without credentials or paths")
    _ = u.port
    return "https://" + u.netloc.lower()


def headers(key, identity, server, path, body):
    now = int(time.time())
    digest = "sha-256=:" + base64.b64encode(hashlib.sha256(body).digest()).decode() + ":"
    covered = '("@method" "@path" "@authority" "content-digest" "content-type" "x-bearings-key")'
    params = (
        f'{covered};created={now};keyid="{identity}";alg="ed25519";expires={now + 300};'
        f'nonce="{uuid.uuid4()}";tag="{TAG}"'
    )
    values = {
        "@method": "POST",
        "@path": path,
        "@authority": urlsplit(server).netloc.lower(),
        "content-digest": digest,
        "content-type": "application/json",
        "x-bearings-key": identity,
        "@signature-params": params,
    }
    base = "\n".join(f'"{k}": {v}' for k, v in values.items()).encode()
    return {
        "Content-Type": "application/json",
        "Content-Digest": digest,
        "X-Bearings-Key": identity,
        "Signature-Input": "bearings=" + params,
        "Signature": "bearings=:" + base64.b64encode(key.sign(base)).decode() + ":",
    }


def send(state, path, body, identity=None, bearer=None):
    if len(body) > MAX_BODY:
        raise ValueError("Request exceeds size limit")
    server = origin(state["url"])
    u = urlsplit(server)
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(state["seed"], validate=True))
    hs = headers(key, identity or "device:" + state["device_id"], server, path, body)
    if bearer:
        hs["Authorization"] = "Bearer " + bearer
    context = ssl.create_default_context()
    if state.get("ca_file"):
        context.load_verify_locations(state["ca_file"])
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    connection = http.client.HTTPSConnection(u.hostname, u.port, timeout=20, context=context)
    try:
        connection.request("POST", path, body, hs)
        response = connection.getresponse()
        raw = response.read(65537)
        if response.status not in (200, 202):
            raise ValueError(f"Server refused request (HTTP {response.status}); local input retained")
        if len(raw) > 65536 or response.getheader("Content-Type", "").split(";")[0] != "application/json":
            raise ValueError("Invalid server response")
        return json.loads(raw)
    finally:
        connection.close()


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def protect(raw, decrypt=False):
    """User-scoped Windows DPAPI, authenticated encryption; no machine-wide flag."""
    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(Blob),
    ]
    fn.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise ValueError("Windows user-protected state unavailable; key was not replaced")
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(result.data)


class Store:
    def __init__(self, path, initialize=False):
        self.path = Path(path).absolute()
        self.lock = None
        self.initialize = initialize

    def __enter__(self):
        import msvcrt

        if self.initialize:
            self.path.mkdir(parents=True, exist_ok=True)
        for part in (self.path, *self.path.parents):
            if part.is_symlink() or part.is_junction():
                raise ValueError("State path must not contain links or junctions")
        for name in ("state.dpapi", "lock"):
            file = self.path / name
            if file.is_symlink() or file.is_junction():
                raise ValueError("State files must not be links")
        self.lock = os.fdopen(os.open(self.path / "lock", os.O_RDWR | os.O_CREAT, 0o600), "r+b")
        try:
            self.lock.seek(0)
            self.lock.write(b"0")
            self.lock.flush()
            self.lock.seek(0)
            msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            state_file = self.path / "state.dpapi"
            if state_file.exists():
                if state_file.stat().st_size > 70_000_000:
                    raise ValueError("State exceeds size limit")
                self.data = json.loads(protect(state_file.read_bytes(), decrypt=True))
            elif self.initialize:
                key = Ed25519PrivateKey.generate()
                self.data = dict(seed=base64.b64encode(key.private_bytes_raw()).decode(), counter=0, queue=[])
                self.save()
            else:
                raise ValueError("Missing state; run init first")
            return self
        except BaseException:
            self.lock.close()
            raise

    def __exit__(self, *_):
        self.lock.close()

    def save(self):
        raw = protect(packed(self.data))
        fd, name = tempfile.mkstemp(prefix=".bearings-", dir=self.path)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path / "state.dpapi")
        finally:
            Path(name).unlink(missing_ok=True)


def public(state):
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(state["seed"], validate=True))
    return base64.b64encode(key.public_key().public_bytes_raw()).decode()


def valid_uuid(value):
    return isinstance(value, str) and str(uuid.UUID(value)) == value


def future(value):
    expiry = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return expiry.tzinfo is not None and expiry > datetime.now(timezone.utc)


def enroll(store, grant, ca_file):
    s = store.data
    if s.get("device_id"):
        raise ValueError("Already enrolled; revoke and review replacement explicitly")
    if (
        grant["schema"] != "bearings.agent.grant.v1"
        or grant["public_key"] != public(s)
        or not valid_uuid(grant["asset_id"])
        or grant.get("register_host")
        or not future(grant["expires_at"])
    ):
        raise ValueError("Use an unexpired public-key-bound grant for an existing asset")
    token = grant["grant"]
    if not re.fullmatch(r"[0-9a-f-]{36}\.[A-Za-z0-9_-]{32,64}", token):
        raise ValueError("Invalid enrollment token")
    identity = "enroll:" + token.split(".")[0]
    destination = origin(grant["url"])
    if s.get("pending") and (s["url"] != destination or s["pending"]["identity"] != identity):
        raise ValueError("Different enrollment already pending; state retained")
    if not s.get("pending"):
        s.update(
            url=destination,
            ca_file=str(Path(ca_file).resolve()) if ca_file else "",
            pending=dict(
                identity=identity, body=dict(schema="bearings.agent.enroll.v1", request_id=str(uuid.uuid4()))
            ),
        )
        store.save()
    result = send(s, "/api/v1/agent/enroll/", packed(s["pending"]["body"]), identity, token)
    if (
        result.get("schema") != "bearings.agent.enrolled.v1"
        or not valid_uuid(result.get("device_id"))
        or result.get("asset_id") != grant["asset_id"]
        or not future(result["expires_at"])
    ):
        raise ValueError("Invalid enrollment receipt; pending state retained")
    s.update(device_id=result["device_id"], expires_at=result["expires_at"])
    del s["pending"]
    store.save()
    return result


def ready(state):
    if not state.get("device_id") or not future(state["expires_at"]):
        raise ValueError("Device not enrolled or credential expired; state retained")


def enqueue(store, report):
    s = store.data
    ready(s)
    if len(s["queue"]) >= 64 or s["counter"] >= 2**63 - 2:
        raise ValueError("Outbox full or sequence exhausted; retained input requires review")
    report["sequence"] = s["counter"] + 1
    body = packed(report)
    if len(body) > MAX_BODY:
        raise ValueError("Report exceeds size limit")
    s["counter"] = report["sequence"]
    s["queue"].append(body.decode())
    store.save()


def receipt(result, report_id):
    if (
        result.get("schema") != "bearings.agent.receipt.v1"
        or result.get("report_id") != report_id
        or result.get("status") not in {"pending", "applied", "rejected", "superseded"}
    ):
        raise ValueError("Invalid receipt; local input retained")


def flush(store):
    s = store.data
    ready(s)
    result = None
    while s["queue"]:
        body = s["queue"][0].encode()
        report = json.loads(body)
        result = send(s, "/api/v1/agent/reports/", body)
        receipt(result, report["report_id"])
        if (
            result.get("sequence") != report["sequence"]
            or result.get("body_sha256") != hashlib.sha256(body).hexdigest()
        ):
            raise ValueError("Receipt does not acknowledge exact queued report")
        s["receipt"] = result
        s["queue"].pop(0)
        store.save()
        if result["status"] == "rejected":
            raise ValueError("Report rejected; inspect retained receipt")
        if s["queue"]:
            time.sleep(11)  # Respect the receiver's device admission interval.
    return result or {"state": "outbox_empty"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["init", "enroll", "collect", "report", "flush", "status", "watch"]
    )
    parser.add_argument(
        "--state-dir", default=str(Path(os.environ.get("LOCALAPPDATA", ".")) / "Bearings" / "Windows")
    )
    parser.add_argument(
        "--code", action="store_true", help="Hidden prompt for an existing-asset registration code"
    )
    parser.add_argument("--ca-file")
    parser.add_argument("--interval", type=int, default=21600, help="Watch interval in seconds (minimum 600)")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise ValueError("Run this client on the Windows endpoint")
    if args.command == "collect":
        print(json.dumps(collect(), ensure_ascii=True, indent=2))
        return
    if args.interval < 600:
        raise ValueError("Minimum reporting interval is 600 seconds")
    if args.command == "watch":
        while True:
            try:
                with Store(args.state_dir) as store:
                    flush(store)
                    enqueue(store, collect())
                    print(json.dumps(flush(store)), flush=True)
            except (OSError, ValueError, KeyError, ssl.SSLError, http.client.HTTPException):
                print(
                    "Inventory cycle failed; last-known state retained; retry next interval",
                    file=sys.stderr,
                    flush=True,
                )
            time.sleep(args.interval)
    with Store(args.state_dir, initialize=args.command == "init") as store:
        if args.command == "init":
            result = {"public_key": public(store.data), "enrolled": bool(store.data.get("device_id"))}
        elif args.command == "enroll":
            import getpass

            if not args.code:
                raise ValueError("Use enroll --code and the hidden registration-code prompt")
            code = getpass.getpass("Registration code: ").strip()
            if not code.startswith("bearings-enroll-v1.") or len(code) > 16000:
                raise ValueError("Invalid registration code")
            raw = code.split(".", 1)[1]
            grant = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
            result = enroll(store, grant, args.ca_file)
        elif args.command == "report":
            flush(store)
            enqueue(store, collect())
            result = flush(store)
        elif args.command == "flush":
            result = flush(store)
        else:
            ready(store.data)
            report_id = store.data.get("receipt", {}).get("report_id")
            if not report_id:
                raise ValueError("No previous receipt")
            result = send(
                store.data,
                "/api/v1/agent/status/",
                packed(dict(schema="bearings.agent.status.v1", report_id=report_id)),
            )
            receipt(result, report_id)
        print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, ssl.SSLError, http.client.HTTPException):
        print(
            "Operation failed; check enrollment, permissions, HTTPS trust and retained local state",
            file=sys.stderr,
        )
        sys.exit(1)
