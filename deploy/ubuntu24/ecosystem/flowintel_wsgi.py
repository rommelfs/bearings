"""Native FlowIntel adapter: private session socket and explicit OIDC bindings."""

from redis import Redis
from app import create_app as upstream_create_app
from flowintel_sso import install


def create_app():
    app = upstream_create_app()
    app.session_interface.client = Redis(unix_socket_path="/run/bearings-flowintel-redis/redis.sock")
    return install(app)
