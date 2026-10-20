"""Runtime-only overlay of the pinned upstream configuration; secrets come from files."""

from pathlib import Path

exec(compile(Path(__file__).with_name("config.py.default").read_text(), "flowintel-default-config", "exec"))
for cls in globals()["config"].values():
    cls.SESSION_COOKIE_NAME = "flowintelsessionid"
    cls.SESSION_COOKIE_SECURE = True
    cls.SESSION_COOKIE_HTTPONLY = True
    cls.SESSION_COOKIE_SAMESITE = "Lax"
    cls.BEHIND_PROXY = True
    cls.PROXY_X_FOR = 1
    cls.PROXY_X_PROTO = 1
    cls.PROXY_X_HOST = 1
    cls.LIMIT_USER_VIEW_TO_ORG = True
    cls.ENABLE_CHATBOT = False
    cls.ENTRA_ID_ENABLED = False
    cls.KEYCLOAK_ENABLED = False
    cls.SIMPLESAML_ENABLED = False
