"""Native CIRCL service identity; captured output contains a private API key."""

import json
import secrets
import string
import sys
import uuid
from app.extensions import db
from app.db_class.db import User, Org, Role
from flowintel_wsgi import create_app

FLAGS = (
    "admin",
    "read_only",
    "org_admin",
    "case_admin",
    "queue_admin",
    "queuer",
    "audit_viewer",
    "template_editor",
    "misp_editor",
    "importer",
)


def provision(data):
    key = uuid.UUID(data["key"]).hex
    actor = User.query.filter_by(email=data["actor"]).one()
    if not actor.is_admin():
        raise ValueError("Existing FlowIntel administrator required")
    email = "bearings-" + key + "@service.invalid"
    name = "Bearings " + key
    saved = data.get("saved")
    if saved:
        user = db.session.get(User, saved["user"])
        org = db.session.get(Org, saved["org"])
        role = db.session.get(Role, saved["role"])
        if (
            not user
            or not org
            or not role
            or user.email != email
            or user.org_id != org.id
            or user.role_id != role.id
            or user.api_key != saved["value"]
            or user.auth_provider != "bearings-service"
            or org.uuid != data["key"]
            or role.name != name
            or any(getattr(role, f) for f in FLAGS)
        ):
            raise ValueError("Retained FlowIntel service policy changed; no restoration")
        return saved
    if (
        User.query.filter_by(email=email).first()
        or Org.query.filter_by(uuid=data["key"]).first()
        or Role.query.filter_by(name=name).first()
    ):
        raise ValueError("Unrecorded native service exists; reconcile without name adoption")
    org = Org(name="CIRCL Bearings", uuid=data["key"], description=name, default_org=False)
    role = Role(name=name, description="Bounded Bearings case bridge", **dict.fromkeys(FLAGS, False))
    db.session.add_all([org, role])
    db.session.flush()
    value = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(60))
    user = User(
        email=email,
        first_name="Bearings",
        last_name="Service",
        org_id=org.id,
        role_id=role.id,
        api_key=value,
        auth_provider="bearings-service",
    )
    user.password = secrets.token_urlsafe(64)
    db.session.add(user)
    db.session.commit()
    return {"user": user.id, "org": org.id, "role": role.id, "value": value}


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        print(json.dumps(provision(json.load(sys.stdin))))
