"""MISP JSON search is POST, but reads only. No push, publish or synchronization-user API."""

import json
import os
import time
import uuid
from .http import ConnectorError, approved_base, request_json

PAGE_SIZE = 10
MAX_EVENTS = 500
MAX_BYTES = 20_000_000
MAX_SECONDS = 30


def snapshot(source):
    source.full_clean()
    if not source.enabled:
        raise ConnectorError("MISP source is disabled")
    token = os.getenv(source.token_env_var, "").strip()
    if not token or "\r" in token or "\n" in token:
        raise ConnectorError("MISP credential reference is unavailable or invalid")
    base = approved_base(source.base_url, source.allow_private)
    started, total_bytes, result, identities, remote_ids = time.monotonic(), 0, [], set(), set()
    identity = request_json(
        "GET",
        base + "/users/view/me",
        headers={"Authorization": token, "Accept": "application/json"},
        timeout=10,
        deadline=started + MAX_SECONDS,
    )
    # The response can contain secrets: whitelist only the pinned ID, never persist/log the response.
    user = identity.get("User", {})
    if not isinstance(user, dict) or str(user.get("id")) != str(source.misp_user_id):
        raise ConnectorError("MISP key owner does not match the pinned personal identity")
    for page in range(1, MAX_EVENTS // PAGE_SIZE + 2):
        if time.monotonic() - started > MAX_SECONDS:
            raise ConnectorError("MISP snapshot time budget exceeded")
        body = request_json(
            "POST",
            base + "/events/restSearch",
            headers={"Authorization": token, "Accept": "application/json"},
            json={
                "returnFormat": "json",
                "page": page,
                "limit": PAGE_SIZE,
                "metadata": False,
                "withAttachments": False,
                "excludeLocalTags": False,
                "deleted": False,
            },
            timeout=10,
            deadline=started + MAX_SECONDS,
        )
        if set(body) != {"response"} or not isinstance(body["response"], list):
            raise ConnectorError("Unsupported MISP event-search envelope; no cached data changed")
        rows = body["response"]
        if len(rows) > PAGE_SIZE:
            raise ConnectorError("MISP ignored the page limit")
        for wrapper in rows:
            event = validate_event(wrapper)
            identity = event["uuid"]
            if identity in identities or event["id"] in remote_ids:
                raise ConnectorError("Repeated MISP page/event identity; snapshot refused")
            identities.add(identity)
            remote_ids.add(event["id"])
            total_bytes += len(json.dumps(event, ensure_ascii=True).encode())
            if total_bytes > MAX_BYTES or len(result) >= MAX_EVENTS:
                raise ConnectorError(
                    "MISP snapshot exceeds pilot bounds; use a dedicated scoped read account"
                )
            result.append(event)
        if len(rows) < PAGE_SIZE:
            return result
    raise ConnectorError("MISP snapshot pagination did not complete")


def validate_event(wrapper):
    try:
        if not isinstance(wrapper, dict) or set(wrapper) != {"Event"}:
            raise ValueError()
        event = wrapper["Event"]
        if not isinstance(event, dict):
            raise ValueError()
        uuid.UUID(event["uuid"])
        if str(uuid.UUID(event["uuid"])) != event["uuid"]:
            raise ValueError()
        for field in ["id", "timestamp"]:
            value = event[field]
            if isinstance(value, bool) or not str(value).isdigit() or not 0 < int(value) < 2**63:
                raise ValueError()
        if not isinstance(event["info"], str) or not 1 <= len(event["info"]) <= 1000:
            raise ValueError()
        if str(event["distribution"]) not in {"0", "1", "2", "3", "4"}:
            raise ValueError()
        if event.get("deleted") not in (None, False, 0, "0"):
            raise ValueError()
        for key in ["Attribute", "Object", "Tag", "Galaxy"]:
            if key in event and not isinstance(event[key], list):
                raise ValueError()
        # Preserve unmodified nested policy/evidence, including unrecognized fields. No redistribution inference.
        return event
    except (KeyError, ValueError, TypeError, AttributeError):
        raise ConnectorError("Invalid/incomplete MISP event; entire snapshot retained unchanged") from None
