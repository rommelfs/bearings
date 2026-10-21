"""Run in the pinned FlowIntel runtime, with an isolated SQLite database and cache."""
# ruff: noqa: E402 -- this standalone test bootstraps the pinned upstream module path.

import json
import os
import secrets
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path[:0] = ["/adapter", "/home/flowintel/app"]

from flask import Flask, jsonify, render_template_string
from flask_login import current_user
from flask_session import Session
from cachelib import FileSystemCache
from flask_wtf import CSRFProtect
from jinja2 import DictLoader

from app.extensions import db, login_manager
from app.db_class.db import Org, Role, User
import flowintel_sso as sso


class FlowSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            SECRET_KEY=secrets.token_urlsafe(32),
            SQLALCHEMY_DATABASE_URI="sqlite://",
            SESSION_TYPE="cachelib",
            SESSION_CACHELIB=FileSystemCache(self.temp.name),
            WTF_CSRF_ENABLED=True,
        )
        self.app.jinja_env.loader = DictLoader(
            {"account/login.html": "{% if config.KEYCLOAK_ENABLED %}{% endif %}<form></form>"}
        )
        Session(self.app)
        CSRFProtect(self.app)
        db.init_app(self.app)
        login_manager.init_app(self.app)
        with self.app.app_context():
            db.create_all()
            org = Org(name="Scoped CIRCL", uuid="synthetic-sso-org")
            role = Role(name="Editor")
            db.session.add_all([org, role])
            db.session.flush()
            user = User(
                email="circl-analyst@example.com",
                org_id=org.id,
                role_id=role.id,
                password="synthetic-kept-password",
            )
            db.session.add(user)
            db.session.flush()
            self.user_id, self.org_id, self.role_id = user.id, org.id, role.id
            self.password_hash = user.password_hash
            self.identity = sso.identity_key("https://idp.example/realm", "immutable-sub")
            db.session.execute(
                sso.bindings.insert().values(
                    identity=self.identity, user_id=user.id, enabled=True, generation="initial"
                )
            )
            db.session.commit()

        @self.app.get("/")
        def index():
            return jsonify(authenticated=current_user.is_authenticated, user_id=current_user.get_id())

        @self.app.get("/account/login")
        def login():
            return render_template_string('<input name="csrf_token" value="{{ csrf_token() }}">')

        config = {
            "issuer": "https://idp.example/realm",
            "authorization": "https://idp.example/auth",
            "token": "https://idp.example/token",
            "userinfo": "https://idp.example/user",
            "jwks": "https://idp.example/keys",
            "callback": "https://flow.example/bearings-sso/callback",
            "client": "flowintel",
            "secret": "private-synthetic",
            "ca": "/approved/ca.pem",
        }
        with (
            patch.dict(os.environ, BEARINGS_FLOWINTEL_SSO="1"),
            patch.object(sso, "settings", return_value=config),
        ):
            sso.install(self.app)
        self.browser = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        self.temp.cleanup()

    def login(self, identity=None):
        with self.browser.session_transaction() as saved:
            saved["bearings_oidc_pending"] = {"state": "one"}
        with patch.object(sso.Client, "complete", return_value=identity or self.identity):
            return self.browser.get("/bearings-sso/callback?code=private-code&state=one")

    def test_csrf_post_and_no_automatic_account_or_role_changes(self):
        self.assertEqual(self.browser.get("/bearings-sso/login").status_code, 405)
        self.assertEqual(self.browser.post("/bearings-sso/login").status_code, 400)
        self.assertEqual(self.login().status_code, 302)
        self.assertTrue(self.browser.get("/").json["authenticated"])
        with self.app.app_context():
            user = db.session.get(User, self.user_id)
            self.assertEqual(
                (user.org_id, user.role_id, user.password_hash),
                (self.org_id, self.role_id, self.password_hash),
            )
            self.assertEqual(User.query.count(), 1)
        unknown = self.app.test_client()
        with patch.object(sso.Client, "complete", return_value="foreign-identity"):
            self.assertIn("/account/login", unknown.get("/bearings-sso/callback").location)
        self.assertFalse(unknown.get("/").json["authenticated"])
        with self.browser.session_transaction() as saved:
            self.assertNotIn("private-code", json.dumps(dict(saved)))
            self.assertNotIn("access_token", saved)

    def test_revocation_and_reenable_cannot_revive_old_session(self):
        self.login()
        with self.app.app_context():
            db.session.execute(sso.bindings.update().values(enabled=False, generation="revoked"))
            db.session.commit()
        response = self.browser.get("/")
        self.assertEqual(response.status_code, 302)
        # Save another stale generation as if restoring an old cookie/cache; generation is checked.
        with self.app.app_context():
            db.session.execute(sso.bindings.update().values(enabled=True, generation="explicit-relink"))
            db.session.commit()
        with self.browser.session_transaction() as saved:
            saved["_user_id"] = str(self.user_id)
            saved["bearings_oidc"] = {
                "identity": self.identity,
                "generation": "initial",
                "started": time.time(),
            }
        self.assertEqual(self.browser.get("/").status_code, 302)

    def test_expired_session_and_deleted_account_are_rejected(self):
        self.login()
        with self.browser.session_transaction() as saved:
            saved["bearings_oidc"]["started"] = time.time() - 1801
            saved.modified = True
        self.assertEqual(self.browser.get("/").status_code, 302)
        self.login()
        with self.app.app_context():
            db.session.execute(sso.bindings.delete())
            db.session.delete(db.session.get(User, self.user_id))
            db.session.commit()
        self.assertEqual(self.browser.get("/").status_code, 302)

    def test_disabled_profile_discards_sso_session(self):
        app = Flask("disabled")
        app.secret_key = secrets.token_urlsafe(32)
        login_manager.init_app(app)
        with patch.dict(os.environ, BEARINGS_FLOWINTEL_SSO="0"):
            sso.install(app)
        app.add_url_rule("/", view_func=lambda: "local")
        browser = app.test_client()
        with browser.session_transaction() as saved:
            saved["bearings_oidc"] = {"identity": self.identity}
        self.assertEqual(browser.get("/").status_code, 302)
        self.assertEqual(browser.get("/").data, b"local")


if __name__ == "__main__":
    unittest.main()
