"""Read-only InfoIP connector. Agent/target/scheduler routes are deliberately unsupported."""

import ipaddress
import os
from .http import ConnectorError, UpstreamHTTPError, approved_base, request_json


def infoip(source, ip, start, stop):
    source.full_clean()
    if not source.enabled or source.fixture:
        raise ConnectorError("Live reads require an enabled non-fixture Plum source")
    address = ipaddress.ip_address(ip)
    if not address.is_global:
        raise ConnectorError("The InfoIP API supports individual public IP addresses")
    token = os.getenv(source.token_env_var, "").strip()
    if not token:
        raise ConnectorError("Plum API JWT credential reference is unavailable; Agent keys are not supported")
    base = approved_base(source.base_url, source.allow_private)
    try:
        return request_json(
            "GET",
            base.rstrip("/") + "/api/v1/infoip/" + str(address),
            params={"start": start.isoformat(), "stop": stop.isoformat()},
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            timeout=10,
        )
    except UpstreamHTTPError as exc:
        if exc.status_code == 404:
            return None
        raise
