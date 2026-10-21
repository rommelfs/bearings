"""Explicit issuer/subject bindings for the pinned FlowIntel lab. Roles stay local."""

import json
import os
from pathlib import Path
import secrets
import time

from flask import abort, flash, redirect, request, session
from flask_login import current_user, login_user, logout_user
from jinja2 import ChoiceLoader, DictLoader
from sqlalchemy import select

from app.extensions import db
from app.db_class.db import User
from oidc_client import Client, SignInError, identity_key

bindings = db.Table(
    "bearings_oidc_binding",
    db.Column("identity", db.String(64), primary_key=True),
    db.Column("user_id", db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True),
    db.Column("enabled", db.Boolean, nullable=False),
    db.Column("generation", db.String(64), nullable=False),
)


def settings():
    manifest = json.loads(Path("/run/sso/flowintel.json").read_text())
    issuer = manifest["issuer"]
    base = "https://netbox.bearings.test:444/realms/bearings-lab/protocol/openid-connect/"
    if issuer != f"https://localhost:{int(os.environ.get('SSO_PORT', '9444'))}/realms/bearings-lab":
        raise ValueError("Unrecognized bundled issuer")
    return {
        "issuer": issuer,
        "client": "flowintel",
        "secret": Path("/run/sso/client_secret").read_text().strip(),
        "callback": manifest["callback"],
        "ca": "/run/sso/ca-bundle.pem",
        "authorization": issuer + "/protocol/openid-connect/auth",
        **{
            name: base + path
            for name, path in [("token", "token"), ("userinfo", "userinfo"), ("jwks", "certs")]
        },
    }


def provision(app):
    with app.app_context():
        bindings.create(db.engine, checkfirst=True)
        manifest = json.loads(Path("/run/sso/flowintel.json").read_text())
        # This is the existing CIRCL human. Customer and API bridge identities are never linked.
        user = User.query.filter_by(email="circl-analyst@example.com").one()
        identity = identity_key(manifest["issuer"], manifest["subject"])
        existing = (
            db.session.execute(select(bindings).where(bindings.c.identity == identity)).mappings().first()
        )
        if existing and existing["user_id"] != user.id:
            raise RuntimeError("FlowIntel identity changed; refusing reassignment")
        if not existing:
            db.session.execute(
                bindings.insert().values(
                    identity=identity,
                    user_id=user.id,
                    enabled=True,
                    generation=secrets.token_hex(32),
                )
            )
            db.session.commit()
        # Existing disabled bindings, roles, organizations, passwords and keys remain untouched.


def identity_command(app, action):
    """Docker-operator control of the explicit synthetic CIRCL binding, never its role."""
    with app.app_context():
        config = json.loads(Path("/run/sso/flowintel.json").read_text())
        identity = identity_key(config["issuer"], config["subject"])
        user = User.query.filter_by(email="circl-analyst@example.com").one()
        binding = db.session.execute(select(bindings).where(bindings.c.identity == identity)).mappings().one()
        if binding["user_id"] != user.id:
            raise RuntimeError("Retained FlowIntel identity changed; refusing reassignment")
        if action in {"revoke", "enable"}:
            db.session.execute(
                bindings.update()
                .where(bindings.c.identity == identity)
                .values(
                    enabled=action == "enable",
                    generation=secrets.token_hex(32),
                )
            )
            db.session.commit()
            app.logger.warning(
                "Docker operator %s of synthetic FlowIntel OIDC binding for local user ID %s", action, user.id
            )
        elif action != "status":
            raise ValueError("Unknown identity action")
        enabled = db.session.execute(
            select(bindings.c.enabled).where(bindings.c.identity == identity)
        ).scalar_one()
        print(
            "Synthetic CIRCL FlowIntel SSO binding is "
            + ("enabled" if enabled else "revoked")
            + "; local permissions are unchanged."
        )


def install(app):
    if os.environ.get("BEARINGS_FLOWINTEL_SSO") != "1":

        @app.before_request
        def reject_disabled_sso_session():
            if session.get("bearings_oidc"):
                logout_user()
                session.clear()
                return redirect("/account/login")

        return app
    client = Client(settings())
    source = app.jinja_env.loader.get_source(app.jinja_env, "account/login.html")[0]
    marker = "{% if config.KEYCLOAK_ENABLED %}"
    if source.count(marker) != 1:
        raise RuntimeError("Upstream login template changed; refusing unsafe SSO injection")
    # The upstream login is already inside a CSRF-protected form. Use a separate, non-nested form.
    source = source.replace(
        "</form>",
        """</form>
        <form method="post" action="/bearings-sso/login" class="mt-3">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
          <button class="btn btn-outline-light w-100">Sign in with SSO</button>
          <p class="text-light small mt-2">CIRCL case-workflow accounts only. Application permissions remain local.</p>
        </form>""",
        1,
    )
    app.jinja_env.loader = ChoiceLoader([DictLoader({"account/login.html": source}), app.jinja_env.loader])

    @app.post("/bearings-sso/login")
    def bearings_sso_login():
        url, pending = client.begin()
        session["bearings_oidc_pending"] = pending
        app.session_interface.regenerate(session)
        return redirect(url)

    @app.get("/bearings-sso/callback")
    def bearings_sso_callback():
        pending = session.pop("bearings_oidc_pending", None)
        try:
            identity = client.complete(pending, request.args)
            binding = (
                db.session.execute(
                    select(bindings).where(
                        bindings.c.identity == identity,
                        bindings.c.enabled.is_(True),
                    )
                )
                .mappings()
                .first()
            )
            user = db.session.get(User, binding["user_id"]) if binding else None
            if not user:
                raise SignInError("Unapproved identity")
            session.clear()
            login_user(user, remember=False)
            session["bearings_oidc"] = {
                "identity": identity,
                "generation": binding["generation"],
                "started": time.time(),
            }
            app.session_interface.regenerate(session)
            app.logger.info("Approved OIDC sign-in for local FlowIntel user ID %s", user.id)
            return redirect("/")
        except SignInError:
            app.logger.warning("FlowIntel OIDC sign-in denied")
            flash("SSO sign-in failed. An explicitly linked case-workflow account is required.", "error")
            return redirect("/account/login")

    @app.before_request
    def check_sso_session():
        saved = session.get("bearings_oidc")
        if not saved:
            return
        binding = (
            db.session.execute(
                select(bindings).where(
                    bindings.c.identity == saved.get("identity"),
                    bindings.c.enabled.is_(True),
                )
            )
            .mappings()
            .first()
        )
        if (
            not binding
            or binding["generation"] != saved.get("generation")
            or not current_user.is_authenticated
            or current_user.id != binding["user_id"]
            or not 0 <= time.time() - saved.get("started", 0) < 1800
        ):
            logout_user()
            session.clear()
            if request.path.startswith("/api/"):
                abort(401)
            return redirect("/account/login")

    return app
