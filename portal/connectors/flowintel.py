"""Fixed FlowIntel case/task routes only; external text never supplies API destinations."""

import os
import re
from .http import ConnectorError, approved_base, request_json

READ_ROUTES = [
    r"case/all",
    r"case/completed",
    r"case/list_status",
    r"case/[1-9][0-9]*",
    r"case/[1-9][0-9]*/tasks",
    r"case/[1-9][0-9]*/tasks_finished",
]
WRITE_ROUTES = [r"case/create", r"case/[1-9][0-9]*/create_task"]


def api(instance, method, path, *, payload=None):
    if not instance.available:
        raise ConnectorError("FlowIntel connection is disabled")
    instance.full_clean()
    routes = READ_ROUTES if method == "GET" else WRITE_ROUTES if method == "POST" else []
    if not any(re.fullmatch(pattern, path) for pattern in routes):
        raise ConnectorError("Unsupported FlowIntel operation")
    token = os.environ.get(instance.token_env_var, "").strip()
    if not token:
        raise ConnectorError("FlowIntel credential reference is unavailable")
    base = approved_base(instance.base_url, instance.allow_private)
    kwargs = {"headers": {"X-API-KEY": token, "Accept": "application/json"}, "timeout": 8}
    if payload is not None:
        kwargs["json"] = payload
    return request_json(method, base + "/api/" + path, allow_list=True, **kwargs)
