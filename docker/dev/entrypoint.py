"""Runtime entrypoint for the development stack (no secret values in arguments/logs)."""

import os
import json
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
        if re.fullmatch(r"(?:NETBOX|FLOWINTEL|RT|PLUM|FEDERATION)_[A-Z0-9_]*TOKEN", path.name):
            os.environ[path.name] = path.read_text().strip()
    if os.getenv("BEARINGS_SSO_LAB") == "1":
        manifest = json.loads((ROOT / "secrets/oidc-lab.json").read_text())
        os.environ["BEARINGS_SSO_ENABLED"] = "1"
        os.environ["OIDC_ISSUER"] = manifest["issuer"]
        os.environ["OIDC_CLIENT_SECRET"] = (ROOT / "secrets/oidc_client_secret").read_text().strip()
        os.environ["OIDC_CA_BUNDLE"] = str(ROOT / "trust/ca-bundle.pem")
        public = manifest["issuer"] + "/protocol/openid-connect/"
        internal = "https://netbox.bearings.test:444/realms/bearings-lab/protocol/openid-connect/"
        for name, value in {
            "OIDC_AUTHORIZATION_URL": public + "auth",
            "OIDC_TOKEN_URL": internal + "token",
            "OIDC_USERINFO_URL": internal + "userinfo",
            "OIDC_JWKS_URL": internal + "certs",
        }.items():
            os.environ[name] = value
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
        if os.getenv("BEARINGS_FLOWINTEL") == "1":
            call_command("setup_flowintel_lab")
        if os.getenv("BEARINGS_RT") == "1":
            call_command("setup_rt_lab")
        if os.getenv("BEARINGS_SSO_LAB") == "1":
            call_command("setup_sso_lab")
    elif mode == "smoke":
        from docker.dev.smoke import main as smoke

        smoke()
        if os.getenv("BEARINGS_FLOWINTEL") == "1":
            from docker.dev.flowintel_smoke import main as flowintel_smoke

            flowintel_smoke()
        if os.getenv("BEARINGS_RT") == "1":
            from docker.dev.rt_smoke import main as rt_smoke

            rt_smoke()
    elif mode == "worker":
        while True:
            call_command("process_jobs")
            call_command("process_flowintel", all=True, due=True)
            call_command("process_rt_tickets", all=True, due=True)
            call_command("prepare_notifications", due=True)
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
