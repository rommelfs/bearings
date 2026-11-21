"""Run only through the root operator helper under the native FlowIntel identity."""

import argparse
import secrets
from sqlalchemy import inspect, select
from alembic import command
from alembic.config import Config
from app.extensions import db
from app.db_class.db import User
from app.utils.init_db import create_admin
from flowintel_sso import bindings
from oidc_client import identity_key
from flowintel_wsgi import create_app
import os


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    link = sub.add_parser("link-sso")
    link.add_argument("--user", required=True)
    link.add_argument("--actor", required=True, help="Existing FlowIntel administrator email")
    link.add_argument("--subject", required=True)
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        if args.command == "init":
            cfg = Config("migrations/alembic.ini")
            if not inspect(db.engine).has_table("user"):
                db.create_all()
                command.stamp(cfg, "head")
            else:
                command.upgrade(cfg, "head")
            if User.query.first() is None:
                create_admin()
            elif User.query.filter_by(email=os.environ["ADMIN_MAIL"]).first() is None:
                raise ValueError(
                    "Retained bootstrap administrator missing; review without recreating accounts"
                )
            bindings.create(db.engine, checkfirst=True)
            print("FlowIntel schema/recovery account ready. No cases or outbound delivery created.")
            return
        identity = identity_key(os.environ["OIDC_ISSUER"], args.subject)
        actor = User.query.filter_by(email=args.actor).one()
        if not actor.is_admin():
            raise ValueError("Existing FlowIntel administrator required")
        user = User.query.filter_by(email=args.user).one()
        existing = (
            db.session.execute(
                select(bindings).where((bindings.c.identity == identity) | (bindings.c.user_id == user.id))
            )
            .mappings()
            .all()
        )
        if existing:
            raise SystemExit("Binding already exists; inspect it without replacing or re-enabling it")
        db.session.execute(
            bindings.insert().values(
                identity=identity, user_id=user.id, enabled=True, generation=secrets.token_hex(32)
            )
        )
        db.session.commit()
        app.logger.warning(
            "Operator user ID %s linked SSO for local user ID %s; roles unchanged", actor.id, user.id
        )
        print("Explicit FlowIntel SSO binding created; local organization/roles unchanged.")


if __name__ == "__main__":
    main()
