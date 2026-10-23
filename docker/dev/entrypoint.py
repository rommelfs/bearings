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
        canvas_port = int(os.getenv("BEARINGS_CANVAS_PORT", "9441"))
        os.environ["BEARINGS_CANVAS_ORIGIN"] = f"https://localhost:{canvas_port}"
        os.environ["DJANGO_TRUST_PROXY_SSL"] = "1"
        # The retained lab client is narrowly migrated to this HTTPS callback during startup.
        os.environ["OIDC_LAB_CALLBACK"] = f"https://localhost:{canvas_port}/oauth/complete/oidc/"
        frame_origins = [f"https://localhost:{manifest['ports']['netbox']}"]
        for flag, filename in [("BEARINGS_FLOWINTEL", "flowintel.json"), ("BEARINGS_RT", "rt.json")]:
            if os.getenv(flag) == "1":
                frame_origins.append(json.loads((ROOT / "secrets" / filename).read_text())["browser_url"])
        os.environ["BEARINGS_CANVAS_FRAME_ORIGINS"] = json.dumps(frame_origins)
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
        config = json.loads((ROOT / "secrets/connections.json").read_text())
        if config.get("mode") == "bundled" and os.getenv("BEARINGS_SHOWCASE", "1") == "1":
            from portal.demo_data import KEY
            from portal.models import DemoDataset

            if DemoDataset.objects.filter(key=KEY).exists():
                print("Synthetic showcase state retained; no automatic reseeding or account/policy changes.")
            else:
                call_command("seed_showcase")
    elif mode == "smoke":
        from docker.dev.smoke import main as smoke

        smoke()
        if os.getenv("BEARINGS_FLOWINTEL") == "1":
            from docker.dev.flowintel_smoke import main as flowintel_smoke

            flowintel_smoke()
        if os.getenv("BEARINGS_RT") == "1":
            from docker.dev.rt_smoke import main as rt_smoke

            rt_smoke()
        if os.getenv("BEARINGS_RTIR") == "1":
            from docker.dev.rtir_smoke import main as rtir_smoke

            rtir_smoke()
    elif mode == "worker":
        while True:
            call_command("process_jobs")
            call_command("process_flowintel", all=True, due=True)
            call_command("process_rt_tickets", all=True, due=True)
            call_command("prepare_notifications", due=True)
            Path("/tmp/bearings-worker-heartbeat").touch()
            call_command("process_notifications", limit=5)
            Path("/tmp/bearings-worker-heartbeat").touch()
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
