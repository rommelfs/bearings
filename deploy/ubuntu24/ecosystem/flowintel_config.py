"""Pinned upstream configuration, restricted native case-workflow runtime."""

import os
from pathlib import Path

exec(compile(Path(__file__).with_name("config.py.default").read_text(), "upstream-config", "exec"))


def build_db_uri(DB, env_name):
    # Upstream assigns the URI inside Config.init_app(), after loading class
    # attributes. Override that factory so it cannot replace the peer DSN.
    if env_name != "production":
        raise ValueError("Native FlowIntel requires the production environment")
    return "postgresql+psycopg2://bearings_flowintel@/bearings_flowintel?host=/var/run/postgresql"


for cls in globals()["config"].values():
    cls.SESSION_COOKIE_NAME = "flowintelsessionid"
    cls.SESSION_COOKIE_SECURE = cls.SESSION_COOKIE_HTTPONLY = True
    cls.SESSION_COOKIE_SAMESITE = "Lax"
    cls.BEHIND_PROXY = True
    cls.PROXY_X_FOR = cls.PROXY_X_PROTO = cls.PROXY_X_HOST = 1
    cls.LIMIT_USER_VIEW_TO_ORG = True
    cls.ENABLE_CHATBOT = cls.ENTRA_ID_ENABLED = cls.KEYCLOAK_ENABLED = cls.SIMPLESAML_ENABLED = False
    cls.TRUSTED_HOSTS = [os.environ["FLOWINTEL_HOST"]]
