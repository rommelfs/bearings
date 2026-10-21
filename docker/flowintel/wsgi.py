"""Create the pinned upstream app with the optional approved-identity SSO adapter."""

from app import create_app as upstream_create_app


def create_app():
    from flowintel_sso import install

    return install(upstream_create_app())
