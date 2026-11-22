#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Install/update the Linux client from reviewed local artifacts or a trusted HTTPS origin."""

import argparse
import base64
from datetime import datetime, timezone
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
import time
import ssl
import urllib.request
from urllib.parse import urlsplit

UNIT_SHA256 = "aad8acca2d848bd8bf016d3fb30cb94a22cbda96025800f2a897c541b24b5a17"
# Only this exact previously distributed unit may be upgraded automatically.
PREVIOUS_UNIT_SHA256 = {"cbbc6eb75f24bd7ee356dc6718afa271e08fe24c2686fd3c638fc93675562ea1"}
ACCOUNT = "bearings-linux"
CLIENT = Path("/usr/local/bin/bearings-linux")
UNIT = Path("/etc/systemd/system/bearings-linux.service")
STATE = Path("/var/lib/bearings-linux")
CONFIG = Path("/etc/bearings-linux")
LOCK = Path("/run/bearings-linux-installer.lock")
UPDATER = Path("/usr/local/lib/bearings-linux/update.py")
UPDATE_CONFIG = CONFIG / "update.json"
UPDATE_STATE = Path("/var/lib/bearings-linux-updater")
UPDATE_UNIT = UNIT.with_name("bearings-linux-update.service")
UPDATE_TIMER = UNIT.with_name("bearings-linux-update.timer")
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C", "LANG": "C"}
LXC_OVERRIDE = b"[Service]\nPrivateTmp=no\nPrivateDevices=no\nProtectSystem=no\nProtectHome=no\nProtectKernelTunables=no\nProtectKernelModules=no\nProtectControlGroups=no\nProtectKernelLogs=no\nProtectClock=no\nProtectHostname=no\nReadWritePaths=\n"
READ = """import os,stat,sys
fd=os.open(sys.argv[1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
s=os.fstat(fd);limit=int(sys.argv[2])
if not stat.S_ISREG(s.st_mode) or s.st_size>limit: sys.exit(1)
with os.fdopen(fd,'rb') as f: data=f.read(limit+1)
if len(data)>limit: sys.exit(1)
sys.stdout.buffer.write(data)
"""


# Isolated child performs the drop before exec, including on Python 3.8. Avoid
# preexec_fn (unsafe with threads) and subprocess's Python-3.9-only user/group API.
DROP_PRIVILEGES = """import os,sys
os.setgroups([])
os.setgid(int(sys.argv[2]))
os.setuid(int(sys.argv[1]))
os.execve(sys.argv[3],sys.argv[3:],os.environ)
"""


def account_command(args, account):
    command = [str(arg) for arg in args]
    if account is not None:
        command = [
            sys.executable,
            "-I",
            "-c",
            DROP_PRIVILEGES,
            str(account.pw_uid),
            str(account.pw_gid),
            *command,
        ]
    return command


def reviewed_unit(data):
    return hashlib.sha256(data).hexdigest() in PREVIOUS_UNIT_SHA256 | {UNIT_SHA256}


class InstallError(Exception):
    pass


def enrollment_failure(stderr):
    """Recognize only fixed public client errors, never forward arbitrary stderr."""
    if not isinstance(stderr, bytes) or len(stderr) > 1024:
        return ""
    try:
        message = stderr.decode("ascii").strip()
    except UnicodeError:
        return ""
    status = re.fullmatch(r"server refused request \(HTTP ([1-5][0-9]{2})\); input remains local", message)
    if status:
        return (
            "Server refused registration (HTTP "
            + status[1]
            + "); keep the existing key/state and check rollout validity, quota, scope and clock synchronization"
        )
    known = {
        "invalid rollout credential on stdin": "Invalid rollout-key format; paste the complete existing rollout key at the hidden prompt",
        "another rollout is pending; inspect state without resetting the device key": "Another rollout is pending for this device; retry its original rollout key or ask the administrator to reconcile it; do not delete state",
        "HTTPS delivery failed; check connectivity, trusted CA and configured proxy": "Verified HTTPS registration failed; check connectivity, CA trust and configured proxy",
        "local hostname unavailable or too long": "Local hostname unavailable or too long for registration",
        "local interface enumeration failed": "Local interface enumeration failed during registration",
        "local interface addresses could not be read completely": "Local interface addresses could not be read completely during registration",
        "more than 64 configured addresses; narrow enrollment through explicit existing-asset binding": "Host exceeds the registration address limit; use explicit existing-asset enrollment",
        "enrollment grant expired": "Pending enrollment grant expired; ask the administrator to reconcile it without deleting the device identity",
        "manual enrollment already pending": "Manual enrollment is already pending; complete or reconcile it before using a rollout",
        "invalid structured data": "Server returned an unsupported registration response",
    }
    return known.get(message, "")


def run(args, *, account=None, capture=False, input=None):
    try:
        result = subprocess.run(
            account_command(args, account),
            env=ENV,
            **({"stdin": subprocess.DEVNULL} if input is None else {"input": input}),
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE,
            timeout=45,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallError("Local command failed or timed out; no secret output is printed") from exc
    if result.returncode:
        phase = (
            " " + str(args[1])
            if len(args) > 1 and args[1] in {"version", "init", "bootstrap", "enroll"}
            else ""
        )
        detail = ""
        if (
            Path(str(args[0])).name == "bearings-linux"
            and len(args) > 1
            and args[1] in {"bootstrap", "enroll"}
        ):
            detail = enrollment_failure(result.stderr)
        if Path(str(args[0])).name == "systemctl" and len(args) > 1:
            verb = (
                str(args[1])
                if args[1]
                in {"show", "enable", "disable", "start", "stop", "restart", "status", "daemon-reload"}
                else "operation"
            )
            units = [
                str(arg)
                for arg in args[2:]
                if re.fullmatch(r"bearings-linux(?:-[a-z-]+)?\.(?:service|timer)", str(arg))
            ]
            phase = " " + " ".join([verb, *units])
        raise InstallError(
            f"{Path(str(args[0])).name}{phase} failed (exit {result.returncode}); existing device state is retained"
            + (". " + detail if detail else "")
        )
    return result.stdout if capture else b""


def source(path, limit):
    """Read as the invoking sudo user, never grant their paths a privileged file read."""
    try:
        caller = pwd.getpwuid(int(os.environ.get("SUDO_UID", os.getuid())))
        result = subprocess.run(
            account_command(
                [sys.executable, "-I", "-c", READ, str(Path(path).absolute()), str(limit)],
                caller if os.geteuid() == 0 else None,
            ),
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


def running_installer_source():
    """Copy only the script already explicitly executing with administrator privileges.

    An inherited SUDO_UID must not prevent reading that script from /root.
    User-supplied binary/grant/CA paths still go through source()'s UID drop.
    """
    try:
        return run(
            [sys.executable, "-I", "-c", READ, str(Path(__file__).absolute()), str(128 * 1024)],
            capture=True,
        )
    except InstallError as exc:
        raise InstallError(
            "Cannot copy the running installer for automatic updates: keep it as a regular, non-symlink file smaller than 128 KiB"
        ) from exc


def installed_source(path, limit):
    """Read only root-owned installed paths, independently of sudo's invoking user.

    User-supplied files still use source() and its credential drop.
    """
    path = Path(path)
    safe_parent(path.parent)
    if not regular(path):
        raise InstallError("Installed updater input is missing")
    return run([sys.executable, "-I", "-c", READ, path, str(limit)], capture=True)


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


def service_flag(flag, unit="bearings-linux.service"):
    try:
        result = subprocess.run(
            ["/usr/bin/systemctl", flag, "--quiet", unit],
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


def install(binary_path, unit_path, lxc_compatible=False):
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
    if existing_unit is not None and not reviewed_unit(existing_unit):
        raise InstallError(
            "Existing unit differs from the bundled unit; retain it and reconcile explicitly. Use systemd drop-ins for customization"
        )
    lxc_path = UNIT.with_name(UNIT.name + ".d") / "bearings-lxc.conf"
    if lxc_compatible and lxc_path.exists() and source(lxc_path, 16384) != LXC_OVERRIDE:
        raise InstallError("Existing LXC override differs; reconcile without overwriting local policy")
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
    # Validate executable candidates on their destination filesystem. /run and
    # other temporary mounts may deliberately be noexec; retain that policy.
    safe_parent(CLIENT.parent)
    stage = Path(tempfile.mkdtemp(prefix=".bearings-linux-install-", dir=CLIENT.parent))
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
            if existing_unit != unit:
                atomic(UNIT, unit)
            if lxc_compatible:
                atomic(lxc_path, LXC_OVERRIDE)
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


def download(server, ca_file=None, lxc_compatible=False, *, automatic=False, before_install=None):
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
    context = ca_context(
        (installed_source(ca_file, 1024 * 1024) if automatic else source(ca_file, 1024 * 1024))
        if ca_file
        else None
    )

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
    if automatic:
        if records.get("bearings-linux.service") != UNIT_SHA256:
            raise InstallError("Automatic unit upgrade needs an explicitly reviewed local updater")
        status_path = update_state("status.json")
        status = read_update_json(status_path) if regular(status_path, private=True) else {}
        if status.get("rejected_sha256") == records.get(f"bearings-linux-{arch}") and status.get(
            "rejected_unit_sha256"
        ) == records.get("bearings-linux.service"):
            raise InstallError(
                "Previously failed publication quarantined; publish a corrected release or explicitly retry locally"
            )
        if regular(CLIENT) and regular(UNIT):
            if (
                hashlib.sha256(installed_source(CLIENT, 64 * 1024 * 1024)).hexdigest()
                == records.get(f"bearings-linux-{arch}")
                and hashlib.sha256(installed_source(UNIT, 16384)).hexdigest() == UNIT_SHA256
            ):
                return False
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
        if before_install:
            before_install(records[f"bearings-linux-{arch}"], records["bearings-linux.service"])
        install(directory / f"bearings-linux-{arch}", directory / "bearings-linux.service", lxc_compatible)
        return True
    finally:
        for child in directory.iterdir():
            child.unlink()
        directory.rmdir()


def update_time():
    return datetime.now(timezone.utc).isoformat()


def update_state(name):
    safe_parent(UPDATE_STATE)
    return UPDATE_STATE / name


def read_update_json(path):
    safe_parent(path.parent)
    if not regular(path, private=True):
        raise InstallError("Automatic updates are not configured")
    try:
        value = json.loads(installed_source(path, 16384))
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (ValueError, UnicodeError) as exc:
        raise InstallError("Invalid local updater state; retained for review") from exc


def update_status(**fields):
    path = update_state("status.json")
    previous = read_update_json(path) if regular(path, private=True) else {}
    previous.update(fields)
    atomic(path, (json.dumps(previous) + "\n").encode(), 0o600)


def remove_update_file(name):
    update_state(name).unlink()
    descriptor = os.open(UPDATE_STATE, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def clear_pending_update():
    remove_update_file("pending.json")


def checkpoint_update(candidate_sha256, candidate_unit_sha256):
    # Each file and directory is fsynced before the durable pending marker.
    # Backups never contain enrollment keys or agent-owned configuration.
    status_path = update_state("status.json")
    status = read_update_json(status_path) if regular(status_path, private=True) else {}
    if (
        status.get("rejected_sha256") == candidate_sha256
        and status.get("rejected_unit_sha256") == candidate_unit_sha256
    ):
        raise InstallError(
            "Previously failed publication quarantined; publish a corrected release or explicitly retry locally"
        )
    # A new transaction replaces the prior probation baseline, never reuse its backups.
    completed_path = update_state("completed.json")
    if regular(completed_path, private=True):
        remove_update_file("completed.json")
    old_binary = installed_source(CLIENT, 64 * 1024 * 1024)
    old_unit = installed_source(UNIT, 16384)
    if not reviewed_unit(old_unit):
        raise InstallError("Existing main unit is customized; reconcile before automatic updates")
    atomic(update_state("previous-client"), old_binary, 0o700)
    atomic(update_state("previous-unit"), old_unit, 0o600)
    pending = {
        "schema": "bearings.client-update-transaction.v1",
        "candidate_sha256": candidate_sha256,
        "candidate_unit_sha256": candidate_unit_sha256,
        "binary_sha256": hashlib.sha256(old_binary).hexdigest(),
        "unit_sha256": hashlib.sha256(old_unit).hexdigest(),
        "active": service_flag("is-active"),
    }
    atomic(update_state("pending.json"), json.dumps(pending).encode(), 0o600)


def recover_update(*, start_client=True):
    pending_path = update_state("pending.json")
    if not regular(pending_path, private=True):
        completed_path = update_state("completed.json")
        if not start_client or not regular(completed_path, private=True) or not service_flag("is-failed"):
            return False
        completed = read_update_json(completed_path)
        try:
            age = (
                datetime.now(timezone.utc).timestamp()
                - datetime.fromisoformat(completed["completed_at"]).timestamp()
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InstallError("Invalid updater probation record; operator review required") from exc
        if (
            not 0 <= age <= 86400
            or not regular(CLIENT)
            or hashlib.sha256(installed_source(CLIENT, 64 * 1024 * 1024)).hexdigest()
            != completed.get("candidate_sha256")
        ):
            return False
        atomic(pending_path, json.dumps(completed).encode(), 0o600)
    pending = read_update_json(pending_path)
    if (
        pending.get("schema") != "bearings.client-update-transaction.v1"
        or type(pending.get("active")) is not bool
    ):
        raise InstallError("Invalid updater recovery marker; operator review required")
    if not regular(update_state("previous-client"), private=True) or not regular(
        update_state("previous-unit"), private=True
    ):
        raise InstallError("Updater recovery backups are missing")
    binary = installed_source(update_state("previous-client"), 64 * 1024 * 1024)
    unit = installed_source(update_state("previous-unit"), 16384)
    if (
        hashlib.sha256(binary).hexdigest() != pending.get("binary_sha256")
        or hashlib.sha256(unit).hexdigest() != pending.get("unit_sha256")
        or not reviewed_unit(unit)
    ):
        raise InstallError("Updater recovery checksum failed; backups retained for review")
    changed = (
        not regular(CLIENT)
        or hashlib.sha256(installed_source(CLIENT, 64 * 1024 * 1024)).hexdigest() != pending["binary_sha256"]
        or not regular(UNIT)
        or hashlib.sha256(installed_source(UNIT, 16384)).hexdigest() != pending["unit_sha256"]
    )
    active = service_flag("is-active")
    if changed:
        if active:
            systemctl("stop", "bearings-linux.service")
        atomic(CLIENT, binary, 0o755)
        atomic(UNIT, unit)
        systemctl("daemon-reload")
    if pending["active"] and start_client:
        if changed or not active:
            systemctl("start", "bearings-linux.service")
        if not service_flag("is-active"):
            raise InstallError("Previous client could not be restarted; recovery marker retained")
    elif service_flag("is-active"):
        systemctl("stop", "bearings-linux.service")
    update_status(
        result="rolled_back",
        recovered_at=update_time(),
        rejected_sha256=pending.get("candidate_sha256"),
        rejected_unit_sha256=pending.get("candidate_unit_sha256"),
    )
    clear_pending_update()
    completed_path = update_state("completed.json")
    if regular(completed_path, private=True):
        remove_update_file("completed.json")
    return True


def configure_updates(server, ca_file=None):
    # Only a local privileged operator enables trust in this fixed origin.
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
    account = lookup_account()
    check_state(account)
    if account is None or not enrolled(account) or not regular(CLIENT) or not regular(UNIT):
        raise InstallError("Install and enroll this device before enabling automatic updates")
    if not reviewed_unit(installed_source(UNIT, 16384)):
        raise InstallError(
            "Reconcile the customized main unit before enabling updates; drop-ins are preserved"
        )
    config = {"schema": "bearings.client-update.v1", "enabled": True, "server": server.rstrip("/")}
    if ca_file:
        raw = source(ca_file, 1024 * 1024)
        ca_context(raw)
        config["ca_file"] = str(CONFIG / "update-ca.pem")
        atomic(Path(config["ca_file"]), raw, 0o600)
    recover_update()
    atomic(UPDATER, running_installer_source(), 0o644)
    atomic(UPDATE_CONFIG, json.dumps(config).encode(), 0o600)
    atomic(
        UPDATE_UNIT,
        b"""# SPDX-License-Identifier: AGPL-3.0-or-later
[Unit]
Description=Update Bearings Linux client from its explicitly trusted HTTPS server
Wants=network-online.target
After=network-online.target
OnFailure=bearings-linux-update-recover.service
StartLimitIntervalSec=1h
StartLimitBurst=3
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 -I /usr/local/lib/bearings-linux/update.py auto-update
User=root
UMask=0077
NoNewPrivileges=yes
TimeoutStartSec=5min
MemoryMax=384M
TasksMax=32
""",
    )
    atomic(
        UPDATE_TIMER,
        b"""# SPDX-License-Identifier: AGPL-3.0-or-later
[Unit]
Description=Daily randomized Bearings Linux client update check
[Timer]
OnActiveSec=15min
OnCalendar=daily
RandomizedDelaySec=4h
Persistent=true
Unit=bearings-linux-update.service
[Install]
WantedBy=timers.target
""",
    )
    atomic(
        UNIT.with_name("bearings-linux-update-recover.service"),
        b"""# SPDX-License-Identifier: AGPL-3.0-or-later
[Unit]
Description=Recover an interrupted Bearings client update locally
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 -I /usr/local/lib/bearings-linux/update.py auto-update-recover
ExecStartPost=/usr/bin/systemctl --no-block start bearings-linux-update-retry.timer
User=root
UMask=0077
NoNewPrivileges=yes
TimeoutStartSec=2min
""",
    )
    atomic(
        UNIT.with_name("bearings-linux-update-retry.timer"),
        b"""# SPDX-License-Identifier: AGPL-3.0-or-later
[Unit]
Description=Retry a failed Bearings client update after local recovery
[Timer]
OnActiveSec=15min
RandomizedDelaySec=5min
RemainAfterElapse=no
Unit=bearings-linux-update.service
""",
    )
    atomic(
        UNIT.with_name("bearings-linux-update-recover-boot.service"),
        b"""# SPDX-License-Identifier: AGPL-3.0-or-later
[Unit]
Description=Restore interrupted Bearings updates before client startup
After=local-fs.target
Before=bearings-linux.service
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 -I /usr/local/lib/bearings-linux/update.py auto-update-recover-boot
RemainAfterExit=yes
User=root
UMask=0077
NoNewPrivileges=yes
TimeoutStartSec=2min
[Install]
WantedBy=multi-user.target
""",
    )
    recovery_dropin = UNIT.with_name(UNIT.name + ".d") / "auto-update-recovery.conf"
    recovery_dependency = b"[Unit]\nOnFailure=bearings-linux-update-recover.service\nRequires=bearings-linux-update-recover-boot.service\nAfter=bearings-linux-update-recover-boot.service\n"
    if regular(recovery_dropin) and installed_source(recovery_dropin, 16384) != recovery_dependency:
        raise InstallError("Existing updater recovery dependency differs; reconcile explicitly")
    atomic(recovery_dropin, recovery_dependency)
    update_status(result="configured", configured_at=update_time())
    systemctl("daemon-reload")


def activate_updates():
    # Boot recovery takes the installer lock itself. Never wait for it while
    # holding that same lock in the configuring parent process.
    systemctl("enable", "--now", "bearings-linux-update-recover-boot.service")
    systemctl("enable", "--now", "bearings-linux-update.timer")
    print(
        "Automatic client updates enabled: daily, randomized up to four hours; existing client state retained."
    )


def automatic_update():
    # Recovery is local and precedes any network access, including after power loss.
    recovered = recover_update()
    config = read_update_json(UPDATE_CONFIG)
    if config.get("schema") != "bearings.client-update.v1" or type(config.get("enabled")) is not bool:
        raise InstallError("Invalid automatic update configuration")
    if not config["enabled"]:
        print("Automatic updates disabled.")
        return
    account = lookup_account()
    check_state(account)
    if account is None or not enrolled(account):
        raise InstallError("Automatic updates require an existing enrolled device; no registration attempted")
    if recovered:
        # Do not immediately reinstall the same failed publication after recovery.
        raise InstallError("Recovered interrupted update; next scheduled attempt will recheck publication")
    update_status(checked_at=update_time(), result="checking", error="")
    try:
        changed = download(
            config["server"], config.get("ca_file"), automatic=True, before_install=checkpoint_update
        )
        if changed:
            pending = read_update_json(update_state("pending.json"))
            if pending["active"]:
                for delay in (1, 2, 4):
                    time.sleep(delay)
                    if not service_flag("is-active"):
                        raise InstallError("Updated client did not remain active during startup checks")
            pending["completed_at"] = update_time()
            atomic(update_state("completed.json"), json.dumps(pending).encode(), 0o600)
            clear_pending_update()
        if service_flag("is-failed"):
            raise InstallError("Client service is failed; no healthy update claimed")
        update_status(result="updated" if changed else "unchanged", succeeded_at=update_time(), error="")
        print(
            "Client update installed and startup checked."
            if changed
            else "Client already matches the published artifacts; no restart."
        )
    except (InstallError, OSError, ValueError, UnicodeError) as exc:
        rolled_back = recover_update()
        reason = str(exc)[:300] if isinstance(exc, InstallError) else type(exc).__name__
        update_status(
            result="rolled_back" if rolled_back else "failed",
            error=reason,
            failed_at=update_time(),
        )
        raise InstallError(
            f"Automatic update failed: {reason}. Prior files/state retained or restored; inspect updater status and service journal."
        ) from exc


def disable_updates():
    recover_update()
    config = read_update_json(UPDATE_CONFIG)
    config["enabled"] = False
    atomic(UPDATE_CONFIG, json.dumps(config).encode(), 0o600)
    systemctl("disable", "--now", "bearings-linux-update.timer")
    print("Automatic updates disabled; installed client and reporting remain unchanged.")


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


def bootstrap(server, ca_path, prompt):
    account = lookup_account()
    if account is None:
        raise InstallError("Install the dedicated service account first")
    check_state(account)
    if enrolled(account):
        run([CLIENT, "bootstrap", "--state-dir", STATE, "--server", server], account=account)
        print("Already enrolled; identity and stopped/running service state retained.")
        return
    if prompt:
        if not sys.stdin.isatty():
            raise InstallError("Use --bootstrap-prompt in a terminal or --bootstrap-stdin for automation")
        try:
            token = getpass.getpass("Company rollout key (hidden): ").encode("ascii")
        except UnicodeError as exc:
            raise InstallError("Invalid rollout credential") from exc
    else:
        token = sys.stdin.buffer.read(151)
    if len(token) > 150:
        raise InstallError("Rollout key exceeds its size limit")
    args = [CLIENT, "bootstrap", "--state-dir", STATE, "--server", server]
    if ca_path:
        ca = source(ca_path, 1024 * 1024)
        ca_context(ca)
        atomic(CONFIG / "ca.pem", ca)
        args += ["--ca-file", CONFIG / "ca.pem"]
    run(args, account=account, input=token)
    systemctl("enable", "bearings-linux.service")
    systemctl("restart", "bearings-linux.service")
    print("Automatic registration confirmed; periodic reporting started.")


def main():
    if sys.version_info < (3, 8):
        raise InstallError("Python 3.8 or newer is required; no installation attempted")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        nargs="?",
        choices=[
            "install",
            "enroll",
            "identity",
            "start",
            "status",
            "auto-update-enable",
            "auto-update",
            "auto-update-disable",
            "auto-update-status",
            "auto-update-recover",
            "auto-update-recover-boot",
            "auto-update-retry",
        ],
        default="install",
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
    rollout = parser.add_mutually_exclusive_group()
    rollout.add_argument(
        "--bootstrap-prompt",
        action="store_true",
        help="Automatic company registration with a hidden rollout-key prompt",
    )
    rollout.add_argument(
        "--bootstrap-stdin",
        action="store_true",
        help="Automatic company registration using rollout key from secret-manager stdin",
    )
    parser.add_argument("--grant-file", type=Path)
    parser.add_argument("--ca-file", type=Path)
    parser.add_argument("--register-host", action="store_true")
    parser.add_argument(
        "--lxc-compatible",
        action="store_true",
        help="Explicitly omit unsupported mount/UTS namespace isolation for this client service; retain non-root and capability limits",
    )
    args = parser.parse_args()
    if platform.system() != "Linux" or os.geteuid() != 0:
        raise InstallError(
            "Run on the target Linux host with sudo python3 install.py (Python 3.8+ and systemd required)"
        )
    if args.action != "enroll" and (args.grant_file or args.code or args.code_stdin or args.register_host):
        parser.error("Registration options belong to enroll")
    if (args.bootstrap_prompt or args.bootstrap_stdin) and (args.action != "install" or not args.server):
        parser.error("Automatic registration requires install --server and exactly one bootstrap input")
    if args.lxc_compatible and args.action != "install":
        parser.error("--lxc-compatible belongs to install")
    if args.binary and args.action != "install":
        parser.error("--binary belongs to install")
    if (
        args.ca_file
        and args.action != "enroll"
        and not (args.action in {"install", "auto-update-enable"} and args.server)
    ):
        parser.error("--ca-file belongs to HTTPS installation or enrollment")
    if args.server and (args.action not in {"install", "auto-update-enable"} or args.binary):
        parser.error("--server belongs to install/auto-update-enable and cannot be combined with --binary")
    if args.action == "auto-update-enable" and not args.server:
        parser.error("auto-update-enable requires --server")
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
        if args.action == "install":
            recover_update()
        if args.action == "install" and args.server:
            download(args.server, args.ca_file, args.lxc_compatible)
            if args.bootstrap_prompt or args.bootstrap_stdin:
                bootstrap(args.server, args.ca_file, args.bootstrap_prompt)
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
            install(binary, unit, args.lxc_compatible)
        elif args.action == "enroll":
            enroll(args.grant_file, args.ca_file, args.register_host, args.code, args.code_stdin)
        elif args.action == "auto-update-enable":
            configure_updates(args.server, args.ca_file)
        elif args.action == "auto-update":
            automatic_update()
        elif args.action in {"auto-update-recover", "auto-update-recover-boot"}:
            recover_update(start_client=args.action != "auto-update-recover-boot")
        elif args.action == "auto-update-retry":
            update_status(rejected_sha256=None, rejected_unit_sha256=None)
            automatic_update()
        elif args.action == "auto-update-disable":
            disable_updates()
        elif args.action == "auto-update-status":
            print(
                json.dumps(
                    {
                        "configuration": read_update_json(UPDATE_CONFIG),
                        "transaction_pending": regular(update_state("pending.json"), private=True),
                        "timer_active": service_flag("is-active", "bearings-linux-update.timer"),
                        "timer_enabled": service_flag("is-enabled", "bearings-linux-update.timer"),
                        "status": read_update_json(update_state("status.json")),
                    }
                )
            )
        elif args.action == "identity":
            identity()
        elif args.action == "start":
            start()
        else:
            systemctl("status", "--no-pager", "bearings-linux.service")
    finally:
        os.close(fd)
    if args.action == "auto-update-enable":
        activate_updates()


if __name__ == "__main__":
    try:
        main()
    except (InstallError, OSError) as exc:
        print(f"Installer stopped: {exc}", file=sys.stderr)
        sys.exit(1)
