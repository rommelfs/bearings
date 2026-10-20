"""Entry point around the compact pinned upstream FlowIntel build. No secret values in argv/logs."""

import json
import os
import shutil
from pathlib import Path
import sys
import uuid

ROOT = Path("/run/flowintel")
APP = Path("/home/flowintel/app")
DATA = Path("/var/lib/bearings-flowintel")


def link_runtime_directory(path, target):
    if path.is_dir() and not path.is_symlink():
        backup = path.with_name(path.name + ".image-original")
        if backup.exists() or backup.is_symlink():
            raise RuntimeError(
                f"Runtime directory backup already exists: {backup}; inspect without deleting data"
            )
        # Overlay filesystems can reject a lower-layer directory rename with EXDEV.
        # shutil.move falls back to preserving the tree by copy and removal.
        shutil.move(str(path), str(backup))
    if path.is_symlink():
        if path.resolve() != target.resolve():
            raise RuntimeError(f"Unexpected runtime directory link: {path}; existing data preserved")
    elif not path.exists():
        path.symlink_to(target)
    else:
        raise RuntimeError(f"Unexpected runtime directory entry: {path}; existing data preserved")


def environment():
    if os.environ.get("DB_HOST") != "flowintel-db" or os.environ.get("BEARINGS_FLOWINTEL_LAB") != "1":
        raise RuntimeError("Initializer is restricted to the isolated bundled FlowIntel database")
    for name, filename in [
        ("DB_PASSWORD", "db_password"),
        ("SECRET_KEY", "secret_key"),
        ("ADMIN_PASSWORD", "demo_password"),
    ]:
        os.environ[name] = (ROOT / filename).read_text().strip()
    sys.path.insert(0, str(APP))
    os.chdir(APP)
    # Persist only runtime data; source, private configuration and secrets remain separate.
    DATA.mkdir(exist_ok=True)
    for name in ["logs", "history", "uploads"]:
        target = DATA / name
        target.mkdir(exist_ok=True)
        if os.getuid() == 0:
            os.chown(target, 10000, 0)
        link_runtime_directory(APP / name, target)


def initialize():
    from app import create_app
    from app.extensions import db
    from app.db_class.db import User, Org
    from app.utils.init_db import create_admin, create_editor_role, create_read_only_role
    from app.utils.utils import generate_api_key
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import inspect

    app = create_app()
    with app.app_context():
        cfg = Config("migrations/alembic.ini")
        if not inspect(db.engine).has_table("user"):
            # Match the pinned upstream's fresh-schema initialization path.
            db.create_all()
            command.stamp(cfg, "head")
        else:
            command.upgrade(cfg, "head")
        create_admin()
        role = create_editor_role()
        marker = str(uuid.uuid5(uuid.NAMESPACE_URL, "bearings-flowintel-lab/circl"))
        org = Org.query.filter_by(uuid=marker).first()
        if org is None:
            org = Org(
                name="CIRCL Bearings lab (SYNTHETIC)",
                uuid=marker,
                description="Synthetic pilot; customer users are not provisioned",
                default_org=False,
            )
            db.session.add(org)
            db.session.commit()
        for email, name in [
            ("bearings-bridge@example.invalid", "Bearings bridge"),
            ("circl-analyst@example.com", "CIRCL analyst"),
        ]:
            user = User.query.filter_by(email=email).first()
            if user is None:
                user = User(
                    first_name=name,
                    last_name="SYNTHETIC",
                    email=email,
                    password=os.environ["ADMIN_PASSWORD"] if name == "CIRCL analyst" else generate_api_key(),
                    role_id=role.id,
                    org_id=org.id,
                    api_key=generate_api_key(),
                )
                db.session.add(user)
                db.session.commit()
            if email == "bearings-bridge@example.invalid":
                if user.role_id != role.id or user.org_id != org.id:
                    raise RuntimeError("Bridge identity/role changed; preserved without privilege reset")
                token = Path("/run/bearings/secrets/FLOWINTEL_BUNDLED_TOKEN")
                if token.exists() and token.read_text().strip() != user.api_key:
                    raise RuntimeError(
                        "Bridge database key differs from retained secret; investigate without replacing either"
                    )
                token.write_text(user.api_key + "\n")
                token.chmod(0o600)
                app_uid = int(Path("/run/bearings/secrets/app_uid").read_text())
                os.chown(token, app_uid, 0)
        outsider_marker = str(uuid.uuid5(uuid.NAMESPACE_URL, "bearings-flowintel-lab/isolation-probe"))
        outsider_org = Org.query.filter_by(uuid=outsider_marker).first()
        if outsider_org is None:
            outsider_org = Org(
                name="Isolation probe (SYNTHETIC)",
                uuid=outsider_marker,
                description="No customer data; read-only lab isolation test",
                default_org=False,
            )
            db.session.add(outsider_org)
            db.session.commit()
        outsider = User.query.filter_by(email="isolation-probe@example.invalid").first()
        if outsider is None:
            outsider = User(
                first_name="Isolation probe",
                last_name="SYNTHETIC",
                email="isolation-probe@example.invalid",
                password=generate_api_key(),
                api_key=generate_api_key(),
                org_id=outsider_org.id,
                role_id=create_read_only_role().id,
            )
            db.session.add(outsider)
            db.session.commit()
        if outsider.org_id != outsider_org.id or not outsider.read_only():
            raise RuntimeError("Isolation probe identity changed; preserved without privilege reset")
        probe_key = Path("/run/bearings/secrets/FLOWINTEL_LAB_OUTSIDER_TOKEN")
        probe_key.write_text(outsider.api_key + "\n")
        probe_key.chmod(0o600)
        os.chown(probe_key, int(Path("/run/bearings/secrets/app_uid").read_text()), 0)
        config = Path("/run/bearings/secrets/flowintel.json")
        config.write_text(
            json.dumps(
                {
                    "base_url": "https://flowintel.bearings.test",
                    "browser_url": os.environ["BEARINGS_FLOWINTEL_BROWSER_URL"],
                    "bearings_url": os.environ["BEARINGS_BROWSER_URL"],
                    "service_org_id": org.id,
                }
            )
        )
        config.chmod(0o644)
    for path in [DATA, *DATA.rglob("*")]:
        os.chown(path, 10000, 0, follow_symlinks=False)
    print(
        "FlowIntel schema and synthetic CIRCL identities ready; credentials and policies preserved. No SMTP/webhooks enabled."
    )


def main():
    environment()
    if sys.argv[1] == "init":
        initialize()
    else:
        os.execv(
            "/home/flowintel/venv/bin/gunicorn",
            [
                "gunicorn",
                "--bind",
                "0.0.0.0:7006",
                "--workers",
                "2",
                "--access-logfile",
                "-",
                "app:create_app()",
            ],
        )


if __name__ == "__main__":
    main()
