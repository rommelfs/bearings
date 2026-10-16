"""Public CC0 MONARC catalog reads; no inferred CVE mapping or remote schema resolution."""

import re
import uuid
from urllib.parse import urlsplit
from django.conf import settings
from .http import ConnectorError, approved_base, request_json

SCHEMAS = {
    "risk": "46a32545-94c5-4bcc-88bf-e65973556f7e",
    "asset": "76315a94-50a4-4358-a844-f5eae7e7e141",
    "threat": "9b9e44b1-a943-4f95-b0c3-df1015063a10",
    "vulnerability": "023efe2b-5f7f-43c0-b858-97877b5a1f75",
}


def number(value):
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"0|[1-9][0-9]{0,5}", value):
        return int(value)
    raise ConnectorError("Invalid MOSP paging metadata")


def text(value, limit=20000):
    if not isinstance(value, str) or len(value) > limit:
        raise ConnectorError("Invalid MOSP text field")
    return value


def identity(value):
    try:
        return str(uuid.UUID(value)) if isinstance(value, str) else _invalid_uuid()
    except ValueError:
        raise ConnectorError("Invalid MOSP UUID") from None


def _invalid_uuid():
    raise ConnectorError("Invalid MOSP UUID")


def pages(source, endpoint, params):
    if not source.enabled:
        raise ConnectorError("MOSP source is disabled")
    base = approved_base(source.base_url, proxy_dns=settings.MOSP_PROXY_DNS)
    result, ids, expected = [], set(), None
    for page in range(1, 101):
        data = request_json(
            "GET", base + "/api/v2/" + endpoint + "/", params={**params, "page": page, "per_page": 100}
        )
        meta, rows = data.get("metadata"), data.get("data")
        if not isinstance(meta, dict) or not isinstance(rows, list):
            raise ConnectorError("Invalid MOSP page")
        count = number(meta.get("count"))
        if count > 10000 or number(meta.get("offset")) != page - 1 or number(meta.get("limit")) != 100:
            raise ConnectorError("Invalid or oversized MOSP page")
        if expected is None:
            expected = count
        if count != expected or len(rows) > 100:
            raise ConnectorError("MOSP changed during pagination")
        for row in rows:
            if (
                not isinstance(row, dict)
                or type(row.get("id")) is not int
                or row["id"] < 1
                or row["id"] in ids
            ):
                raise ConnectorError("Invalid or duplicate MOSP identity")
            ids.add(row["id"])
            result.append(row)
        if len(result) == count:
            return result
        if not rows or len(result) > count:
            raise ConnectorError("Incomplete MOSP page")
    raise ConnectorError("MOSP page bound reached")


def schemas(source):
    result = {}
    for row in pages(source, "schema", {}):
        owner, schema = row.get("organization"), row.get("json_schema")
        if (
            not isinstance(owner, dict)
            or owner.get("name") != source.publisher
            or not isinstance(schema, dict)
        ):
            continue
        identifier = schema.get("$id")
        if not isinstance(identifier, str):
            continue
        try:
            uid = urlsplit(identifier).path.rstrip("/").split("/")[-1]
        except ValueError:
            raise ConnectorError("Invalid MOSP schema identifier") from None
        for kind, expected in SCHEMAS.items():
            if uid == expected:
                if kind in result:
                    raise ConnectorError("Ambiguous MOSP schema")
                result[kind] = row["id"]
    if set(result) != set(SCHEMAS):
        raise ConnectorError("Required MONARC schemas are unavailable")
    return result


def normalize(source, kind, row, schema_id, expected_uuid=None):
    owner, data = row.get("organization"), row.get("json_object")
    if (
        not isinstance(owner, dict)
        or owner.get("name") != source.publisher
        or not isinstance(data, dict)
        or row.get("schema_id") != schema_id
    ):
        raise ConnectorError("MOSP publisher or schema mismatch")
    licenses = row.get("licenses")
    if (
        not isinstance(licenses, list)
        or not licenses
        or any(not isinstance(v, dict) or v.get("license_id") != "CC0-1.0" for v in licenses)
    ):
        raise ConnectorError("Only explicitly CC0-licensed MONARC objects are supported")
    uid = identity(data.get("uuid"))
    if expected_uuid is not None and uid != str(expected_uuid):
        raise ConnectorError("MOSP object identity mismatch")
    version = data.get("version")
    if version is not None and (type(version) is not int or version < 1):
        raise ConnectorError("Invalid MOSP version")
    selected = {"uuid": uid, "version": version}
    if kind == "risk":
        for field in ["asset", "threat", "vulnerability"]:
            selected[field] = identity(data.get(field))
        measures = data.get("measures", [])
        if not isinstance(measures, list) or len(measures) > 100:
            raise ConnectorError("Invalid MOSP measures")
        selected["measures"] = [identity(value) for value in measures]
    else:
        if data.get("language") != source.language:
            raise ConnectorError("MOSP language mismatch")
        for field in ["label", "description", "language", "code"]:
            selected[field] = text(data.get(field, ""))
    return {
        "uuid": uid,
        "id": row["id"],
        "kind": kind,
        "schema_uuid": SCHEMAS[kind],
        "publisher": source.publisher,
        "licenses": ["CC0-1.0"],
        "name": text(row.get("name"), 2000),
        "description": text(row.get("description", "")),
        "updated_at": text(row.get("last_updated", ""), 100),
        "data": selected,
    }


def risk_catalog(source):
    schema = schemas(source)
    rows = pages(source, "object", {"organization": source.publisher, "schema_uuid": SCHEMAS["risk"]})
    result = [normalize(source, "risk", row, schema["risk"]) for row in rows]
    if len({r["uuid"] for r in result}) != len(result):
        raise ConnectorError("Ambiguous MONARC risk UUID")
    return result


def risk_bundle(source, risk_uuid):
    schema = schemas(source)

    def get(kind, uid):
        params = {"organization": source.publisher, "uuid": str(uid), "schema_uuid": SCHEMAS[kind]}
        if kind != "risk":
            params["language"] = source.language
        rows = pages(source, "object", params)
        if len(rows) != 1:
            raise ConnectorError("Missing or ambiguous MONARC object")
        return normalize(source, kind, rows[0], schema[kind], uid)

    risk = get("risk", risk_uuid)
    return {
        "risk": risk,
        **{kind: get(kind, risk["data"][kind]) for kind in ["asset", "threat", "vulnerability"]},
    }
