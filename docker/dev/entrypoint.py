"""Runtime entrypoint for the development stack (no secret values in arguments/logs)."""

import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
ROOT = Path("/run/bearings")


def environment():
    os.environ["DJANGO_SECRET_KEY"] = (ROOT / "secrets/django_secret").read_text().strip()
    os.environ["SSL_CERT_FILE"] = str(ROOT / "trust/ca-bundle.pem")
    for path in (ROOT / "secrets").iterdir():
        if re.fullmatch(r"NETBOX_[A-Z0-9_]*TOKEN", path.name):
            os.environ[path.name] = path.read_text().strip()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def main():
    environment()
    mode = sys.argv[1]
    if mode == "manage":
        os.execv(sys.executable, [sys.executable, "manage.py", *sys.argv[2:]])
    if mode == "web":
        os.execv(sys.executable, [sys.executable, "manage.py", "runserver", "0.0.0.0:8000", "--noreload"])
    import django

    django.setup()
    from django.core.management import call_command

    if mode == "init":
        call_command("migrate", interactive=False)
        call_command(
            "setup_dev_stack",
            config=str(ROOT / "secrets/connections.json"),
            password_file=str(ROOT / "secrets/demo_password"),
        )
    elif mode == "smoke":
        from docker.dev.smoke import main as smoke

        smoke()
    elif mode == "worker":
        while True:
            call_command("process_jobs")
            from django.core.management import CommandError

            try:
                call_command("sync_netbox", all=True, due=True)
            except CommandError:
                # Per-source failure is already persisted; other imports and writes keep running.
                pass
            Path("/tmp/bearings-worker-heartbeat").touch()
            try:
                call_command("sync_mosp", all=True, due=True)
            except CommandError:
                pass
            Path("/tmp/bearings-worker-heartbeat").touch()
            time.sleep(5)
    else:
        raise ValueError("Unknown stack entrypoint")


if __name__ == "__main__":
    main()
