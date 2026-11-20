#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Install reviewed local Linux client artifacts; no downloads, compilation or remote commands."""

import argparse
import base64
import fcntl
import grp
import getpass
import hashlib
import json
import os
from pathlib import Path
import platform
import pwd
import re
import stat
import subprocess
import sys
import tempfile
import ssl
import urllib.request
from urllib.parse import urlsplit

UNIT_SHA256 = "cbbc6eb75f24bd7ee356dc6718afa271e08fe24c2686fd3c638fc93675562ea1"
ACCOUNT = "bearings-linux"
CLIENT = Path("/usr/local/bin/bearings-linux")
UNIT = Path("/etc/systemd/system/bearings-linux.service")
STATE = Path("/var/lib/bearings-linux")
CONFIG = Path("/etc/bearings-linux")
LOCK = Path("/run/bearings-linux-installer.lock")
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C", "LANG": "C"}
READ = """import os,stat,sys
fd=os.open(sys.argv[1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
s=os.fstat(fd);limit=int(sys.argv[2])
if not stat.S_ISREG(s.st_mode) or s.st_size>limit: sys.exit(1)
with os.fdopen(fd,'rb') as f: data=f.read(limit+1)
if len(data)>limit: sys.exit(1)
sys.stdout.buffer.write(data)
"""


class InstallError(Exception):
    pass


def run(args, *, account=None, capture=False):
    options = {}
    if account is not None:
        options = {"user": account.pw_uid, "group": account.pw_gid, "extra_groups": []}
    try:
        result = subprocess.run(
            [str(a) for a in args],
            env=ENV,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE,
            timeout=45,
            check=False,
            **options,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallError("Local command failed or timed out; no secret output is printed") from exc
    if result.returncode:
        raise InstallError(f"{Path(str(args[0])).name} failed; existing device state is retained")
    return result.stdout if capture else b""


def source(path, limit):
    """Read as the invoking sudo user, never grant their paths a privileged file read."""
    try:
        caller = pwd.getpwuid(int(os.environ.get("SUDO_UID", os.getuid())))
        result = subprocess.run(
            [sys.executable, "-I", "-c", READ, str(Path(path).absolute()), str(limit)],
            user=caller.pw_uid if os.geteuid() == 0 else None,
            group=caller.pw_gid if os.geteuid() == 0 else None,
            extra_groups=[] if os.geteuid() == 0 else None,
            env=ENV,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        raise InstallError("Cannot safely read the supplied local file") from exc
    if result.returncode:
        raise InstallError("Input must be a readable regular file within its size limit, without a symlink")
    return result.stdout


def safe_parent(path):
    for parent in [path, *path.parents]:
        try:
            info = parent.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise InstallError(f"Unsafe installation directory: {parent}; no permissions changed")


def regular(path, owner=0, private=False):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(info.st_mode) or info.st_uid != owner or info.st_mode & (0o077 if private else 0o022):
        raise InstallError(f"Unsafe existing file: {path}; left unchanged")
    return True


def atomic(path, data, mode=0o644, owner=0, group=0):
    safe_parent(path.parent)
    missing = [parent for parent in [path.parent, *path.parent.parents] if not parent.exists()]
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    for parent in reversed(missing):
        parent.chmod(0o755)
    regular(path, owner=owner)
    fd, name = tempfile.mkstemp(prefix=".bearings-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), mode)
            os.fchown(handle.fileno(), owner, group)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def lookup_account():
    try:
        account = pwd.getpwnam(ACCOUNT)
    except KeyError:
        return None
    try:
        group = grp.getgrgid(account.pw_gid)
    except KeyError as exc:
        raise InstallError("Existing service account has no primary group") from exc
    if (
        account.pw_uid == 0
        or group.gr_name != ACCOUNT
        or group.gr_gid == 0
        or account.pw_dir != str(STATE)
        or account.pw_shell not in ("/usr/sbin/nologin", "/sbin/nologin", "/bin/false")
        or os.getgrouplist(ACCOUNT, account.pw_gid) != [account.pw_gid]
    ):
        raise InstallError(
            "Existing bearings-linux account is not the expected dedicated account; left unchanged"
        )
    return account


def check_state(account):
    if not STATE.exists() and not STATE.is_symlink():
        return
    info = STATE.lstat()
    if (
        account is None
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != account.pw_uid
        or info.st_gid != account.pw_gid
        or info.st_mode & 0o077
    ):
        raise InstallError(
            "Existing state must be owned by the dedicated account and mode 0700; no migration or chmod attempted"
        )


def systemctl(*args, capture=False):
    return run(["/usr/bin/systemctl", *args], capture=capture)


def service_flag(flag):
    try:
        result = subprocess.run(
            ["/usr/bin/systemctl", flag, "--quiet", "bearings-linux.service"],
            env=ENV,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallError("Cannot inspect the existing service state") from exc
    if result.returncode not in (0, 1, 3, 4):
        raise InstallError("Cannot inspect the existing service state")
    return result.returncode == 0


def start():
    account = lookup_account()
    if account is None:
        raise InstallError("Install the client first")
    check_state(account)
    if not enrolled(account):
        raise InstallError("Enroll the device before starting periodic reporting")
    systemctl("enable", "--now", "bearings-linux.service")
    print("Periodic reporting enabled and started.")


def enrolled(account):
    path = STATE / "config.json"
    if not regular(path, account.pw_uid, private=True):
        return False
    data = run([sys.executable, "-I", "-c", READ, path, "8192"], account=account, capture=True)
    try:
        return bool(json.loads(data).get("device_id"))
    except (ValueError, AttributeError) as exc:
        raise InstallError("Existing device configuration is invalid; retained for review") from exc


def install(binary_path, unit_path):
    binary = source(binary_path, 64 * 1024 * 1024)
    arch = {"x86_64": (2, 62), "aarch64": (2, 183)}.get(platform.machine())
    if (
        arch is None
        or len(binary) < 20
        or binary[:4] != b"\x7fELF"
        or binary[4] != arch[0]
        or binary[5] != 1
        or int.from_bytes(binary[18:20], "little") != arch[1]
    ):
        raise InstallError("Supply the Linux ELF client for this architecture (amd64 or arm64)")
    unit = source(unit_path, 16384)
    if hashlib.sha256(unit).hexdigest() != UNIT_SHA256:
        raise InstallError("Use the bundled hardened service unit")
    safe_parent(CLIENT.parent)
    safe_parent(UNIT.parent)
    safe_parent(STATE.parent)
    regular(CLIENT)
    existing_unit = UNIT.read_bytes() if regular(UNIT) else None
    if existing_unit is not None and existing_unit != unit:
        raise InstallError(
            "Existing unit differs from the bundled unit; retain it and reconcile explicitly. Use systemd drop-ins for customization"
        )
    active = service_flag("is-active") if existing_unit else False
    account = lookup_account()
    check_state(account)
    if account is None:
        try:
            grp.getgrnam(ACCOUNT)
        except KeyError:
            pass
        else:
            raise InstallError("Existing service group without the expected account; reconcile explicitly")
        shell = "/usr/sbin/nologin" if Path("/usr/sbin/nologin").exists() else "/sbin/nologin"
        run(["/usr/sbin/useradd", "--system", "--user-group", "--home-dir", STATE, "--shell", shell, ACCOUNT])
        account = lookup_account()
    if not STATE.exists():
        STATE.mkdir(mode=0o700)
        os.chown(STATE, account.pw_uid, account.pw_gid)
    # Validate the candidate as the dedicated account before replacing a running client.
    safe_parent(LOCK.parent)
    stage = Path(tempfile.mkdtemp(prefix="bearings-linux-install-", dir=LOCK.parent))
    try:
        candidate = stage / "bearings-linux"
        candidate.write_bytes(binary)
        candidate.chmod(0o755)
        stage.chmod(0o711)
        run([candidate, "version"], account=account, capture=True)
        public = run([candidate, "init", "--state-dir", STATE], account=account, capture=True)
        try:
            data = json.loads(public)
            if (
                set(data) != {"public_key", "fingerprint_sha256"}
                or len(base64.b64decode(data["public_key"], validate=True)) != 32
            ):
                raise ValueError
        except (ValueError, TypeError, KeyError) as exc:
            raise InstallError("Candidate did not return the expected public identity") from exc
        if not regular(STATE / "key", account.pw_uid, private=True):
            raise InstallError("Candidate did not initialize protected device state")
        try:
            if active:
                systemctl("stop", "bearings-linux.service")
            atomic(CLIENT, binary, 0o755)
            if existing_unit is None:
                atomic(UNIT, unit)
            systemctl("daemon-reload")
        except (InstallError, OSError):
            if active:
                try:
                    systemctl("start", "bearings-linux.service")
                except InstallError:
                    pass
            raise
        print(json.dumps(data))
    finally:
        candidate.unlink(missing_ok=True)
        stage.rmdir()
    if enrolled(account):
        if active:
            systemctl("restart", "bearings-linux.service")
        elif existing_unit is None:
            start()
        print(
            "Updated existing enrolled device; key, queue, configuration, drop-ins and activation state retained."
        )
    else:
        print("Client installed; service stays stopped until enrollment.")
        print(
            "In Bearings: company → Linux inventory reports → paste the public key above → copy registration code."
        )
        print(f"Then: sudo python3 {Path(__file__).name} enroll --code")


def decode_code(code):
    if not code.startswith("bearings-enroll-v1.") or len(code) > 16384:
        raise InstallError("Paste the one-use registration code from Bearings")
    try:
        encoded = code.split(".", 1)[1]
        raw = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
        if len(raw) > 8192 or json.loads(raw).get("schema") != "bearings.agent.grant.v1":
            raise ValueError
        return raw
    except (ValueError, AttributeError) as exc:
        raise InstallError("Invalid registration code; no content printed") from exc


def ca_context(raw=None):
    context = ssl.create_default_context()
    if raw is not None:
        # Never publish a supplied private key or arbitrary file as a readable CA.
        if not re.fullmatch(
            rb"(?:\s*-----BEGIN CERTIFICATE-----\r?\n[A-Za-z0-9+/=\r\n]+-----END CERTIFICATE-----\s*)+", raw
        ):
            raise InstallError("CA input must contain only PEM certificates, never private keys")
        try:
            context.load_verify_locations(cadata=raw.decode("ascii"))
        except (ValueError, UnicodeError, ssl.SSLError) as exc:
            raise InstallError("Invalid PEM CA certificates; no CA file published") from exc
    return context


def download(server, ca_file=None):
    origin = urlsplit(server)
    if (
        origin.scheme != "https"
        or not origin.netloc
        or origin.username
        or origin.password
        or origin.path not in ("", "/")
        or origin.query
        or origin.fragment
    ):
        raise InstallError("Use the trusted Bearings HTTPS origin without a path or credentials")
    context = ca_context(source(ca_file, 1024 * 1024) if ca_file else None)

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise InstallError("Download redirects are refused")

    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context), NoRedirect())

    def fetch(name, limit):
        try:
            with opener.open(server.rstrip("/") + "/downloads/linux/" + name, timeout=20) as response:
                data = response.read(limit + 1)
                if len(data) > limit:
                    raise InstallError("Download exceeds artifact limit")
                return data
        except (OSError, ValueError) as exc:
            raise InstallError("Verified HTTPS download failed; check server artifacts and CA trust") from exc

    manifest = fetch("SHA256SUMS", 16384).decode("ascii")
    records = {}
    for line in manifest.splitlines():
        parts = line.split()
        if (
            len(parts) != 2
            or len(parts[0]) != 64
            or any(c not in "0123456789abcdef" for c in parts[0])
            or parts[1] in records
        ):
            raise InstallError("Invalid artifact manifest")
        records[parts[1]] = parts[0]
    arch = {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine())
    if arch is None:
        raise InstallError("Supported architectures: amd64 and arm64")
    directory = Path(tempfile.mkdtemp(prefix="bearings-linux-download-", dir=LOCK.parent))
    try:
        for name, limit in [(f"bearings-linux-{arch}", 64 * 1024 * 1024), ("bearings-linux.service", 16384)]:
            data = fetch(name, limit)
            if records.get(name) != hashlib.sha256(data).hexdigest():
                raise InstallError("Artifact differs from the server manifest; no installation attempted")
            path = directory / name
            path.write_bytes(data)
            path.chmod(0o644)
        directory.chmod(0o711)
        install(directory / f"bearings-linux-{arch}", directory / "bearings-linux.service")
    finally:
        for child in directory.iterdir():
            child.unlink()
        directory.rmdir()


def identity():
    account = lookup_account()
    if account is None or not regular(STATE / "key", account.pw_uid, private=True):
        raise InstallError("Install first; identity does not create or replace a key")
    check_state(account)
    public = json.loads(run([CLIENT, "init", "--state-dir", STATE], account=account, capture=True))
    print(json.dumps({**public, "enrolled": enrolled(account)}))


def enroll(grant_path, ca_path, register_host, code=False, code_stdin=False):
    if not regular(CLIENT):
        raise InstallError("Install the client first")
    account = lookup_account()
    if account is None:
        raise InstallError("Install the dedicated service account first")
    check_state(account)
    if not regular(STATE / "key", account.pw_uid, private=True):
        raise InstallError("Initialize with install before requesting a public-key-bound grant")
    if enrolled(account):
        raise InstallError(
            "Already enrolled; use the start action to resume service. No credential replacement or key reset attempted"
        )
    if code_stdin:
        raw = sys.stdin.buffer.read(16385)
        if len(raw) > 16384:
            raise InstallError("Registration code exceeds its size limit")
        try:
            grant = decode_code(raw.decode("ascii").strip())
        except UnicodeError as exc:
            raise InstallError("Invalid registration code") from exc
    elif code:
        if not sys.stdin.isatty():
            raise InstallError(
                "Use --code in an interactive terminal; --grant-file remains available for automation"
            )
        grant = decode_code(getpass.getpass("Registration code (hidden): ").strip())
    else:
        grant = source(grant_path, 8192)
    try:
        if json.loads(grant).get("schema") != "bearings.agent.grant.v1":
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise InstallError("Use the grant downloaded from Bearings") from exc
    ca = source(ca_path, 1024 * 1024) if ca_path else None
    if ca is not None:
        ca_context(ca)
        atomic(CONFIG / "ca.pem", ca)
    # A private account-owned directory; no one-use bearer in argv, environment or output.
    safe_parent(LOCK.parent)
    directory = Path(tempfile.mkdtemp(prefix="bearings-linux-enroll-", dir=LOCK.parent))
    try:
        path = directory / "grant.json"
        path.write_bytes(grant)
        path.chmod(0o600)
        os.chown(path, account.pw_uid, account.pw_gid)
        directory.chmod(0o711)
        args = [CLIENT, "enroll", "--state-dir", STATE, "--grant-file", path]
        if ca is not None:
            args += ["--ca-file", CONFIG / "ca.pem"]
        if register_host:
            args.append("--register-host")
        run(args, account=account)
    finally:
        # Remove only the file/directory created by this invocation; never recurse into device state.
        path.unlink(missing_ok=True)
        directory.rmdir()
    systemctl("enable", "bearings-linux.service")
    systemctl("restart", "bearings-linux.service")
    print("Enrollment confirmed; periodic reporting started. Original downloaded grant left unchanged.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", nargs="?", choices=["install", "enroll", "identity", "start", "status"], default="install"
    )
    parser.add_argument("--binary", type=Path)
    parser.add_argument(
        "--server", help="Download architecture-matching artifacts from this trusted HTTPS origin"
    )
    parser.add_argument(
        "--code", action="store_true", help="Paste the one-use registration code at a hidden terminal prompt"
    )
    parser.add_argument(
        "--code-stdin",
        action="store_true",
        help="Read the one-use code from stdin for approved rollout automation",
    )
    parser.add_argument("--grant-file", type=Path)
    parser.add_argument("--ca-file", type=Path)
    parser.add_argument("--register-host", action="store_true")
    args = parser.parse_args()
    if platform.system() != "Linux" or os.geteuid() != 0:
        raise InstallError(
            "Run on the target Linux host with sudo python3 install.py (Python 3.9+ and systemd required)"
        )
    if args.action != "enroll" and (args.grant_file or args.code or args.code_stdin or args.register_host):
        parser.error("Registration options belong to enroll")
    if args.binary and args.action != "install":
        parser.error("--binary belongs to install")
    if args.ca_file and args.action != "enroll" and not (args.action == "install" and args.server):
        parser.error("--ca-file belongs to HTTPS installation or enrollment")
    if args.server and (args.action != "install" or args.binary):
        parser.error("--server belongs to install and cannot be combined with --binary")
    if args.action == "enroll" and sum((bool(args.grant_file), args.code, args.code_stdin)) != 1:
        parser.error("enroll requires exactly one of --code, --code-stdin or --grant-file")
    os.umask(0o077)
    safe_parent(LOCK.parent)
    if LOCK.is_symlink():
        raise InstallError("Unsafe installer lock")
    fd = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
            raise InstallError("Unsafe installer lock")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise InstallError("Another installer is running") from exc
        systemctl("show", "--property=Version", "--value", capture=True)
        if args.action == "install" and args.server:
            download(args.server, args.ca_file)
        elif args.action == "install":
            directory = Path(__file__).resolve().parent
            arch = {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine(), "unsupported")
            candidates = [directory / f"bearings-linux-{arch}"]
            if len(directory.parents) > 1:
                candidates.append(directory.parents[1] / ".local/linux-client" / f"bearings-linux-{arch}")
            binary = args.binary or next((p for p in candidates if p.is_file()), candidates[0])
            unit = directory / "bearings-linux.service"
            if not unit.is_file():
                unit = directory / "systemd/bearings-linux.service"
            install(binary, unit)
        elif args.action == "enroll":
            enroll(args.grant_file, args.ca_file, args.register_host, args.code, args.code_stdin)
        elif args.action == "identity":
            identity()
        elif args.action == "start":
            start()
        else:
            systemctl("status", "--no-pager", "bearings-linux.service")
    finally:
        os.close(fd)


if __name__ == "__main__":
    try:
        main()
    except (InstallError, OSError) as exc:
        print(f"Installer stopped: {exc}", file=sys.stderr)
        sys.exit(1)
