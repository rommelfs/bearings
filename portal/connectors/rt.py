"""RT 5 REST2 contract; fixed routes, token headers and no response-supplied URLs."""

import os
import re
from .http import ConnectorError, approved_base, request_json


def api(instance, method, path, *, payload=None, params=None):
    if not instance.enabled:
        raise ConnectorError("RT connection is disabled")
    instance.full_clean()
    if not (
        (method == "POST" and path == "ticket")
        or (method == "GET" and re.fullmatch(r"tickets|ticket/[1-9][0-9]*", path))
    ):
        raise ConnectorError("Unsupported RT operation")
    token = os.getenv(instance.token_env_var, "").strip()
    if not token:
        raise ConnectorError("RT credential reference is unavailable")
    base = approved_base(instance.base_url, instance.allow_private)
    kwargs = {"headers": {"Authorization": "token " + token, "Accept": "application/json"}, "timeout": 10}
    if payload is not None:
        kwargs["json"] = payload
    if params:
        kwargs["params"] = params
    return request_json(method, base.rstrip("/") + "/REST/2.0/" + path, **kwargs)
