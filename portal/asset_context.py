"""Inventory facts and links from an approved source, never arbitrary upstream URLs."""

import ipaddress
from .connectors.http import ConnectorError, validate_base

REFERENCE_PATHS = {
    "site": "dcim/sites",
    "location": "dcim/locations",
    "rack": "dcim/racks",
    "platform": "dcim/platforms",
    "cluster": "virtualization/clusters",
    "role": "dcim/device-roles",
    "device_type": "dcim/device-types",
    "tenant": "tenancy/tenants",
}


def source_link(asset, path, identity):
    if not asset.source.instance_id or type(identity) is not int or identity < 1:
        return ""
    try:
        instance = asset.source.instance
        base = validate_base(instance.browser_url or instance.base_url).geturl().rstrip("/")
    except ConnectorError:
        return ""
    return f"{base}/{path}/{identity}/"


def label(value, maximum=255):
    return value[:maximum] if isinstance(value, str) else ""


def asset_context(asset):
    data = asset.upstream_data if isinstance(asset.upstream_data, dict) else {}
    result = {
        "name": asset.name,
        "addresses": [],
        "dns_names": [],
        "references": [],
        "position": label(data.get("position")),
        "face": label(data.get("face")),
        "serial": label(data.get("serial")),
        "asset_tag": label(data.get("asset_tag")),
    }
    for field, path in REFERENCE_PATHS.items():
        ref = data.get(field)
        if isinstance(ref, dict):
            entry = {
                "field": field,
                "name": label(ref.get("name")),
                "url": source_link(asset, path, ref.get("id")),
            }
            result[field] = entry
            result["references"].append(entry)
    for field in ["primary_ip4", "primary_ip6"]:
        raw = data.get(field)
        if not isinstance(raw, str):
            continue
        try:
            address = ipaddress.ip_interface(raw)
        except ValueError:
            continue
        version = 4 if field == "primary_ip4" else 6
        if address.version != version:
            continue
        dns = label(data.get(field + "_dns_name"))
        entry = {
            "address": str(address.ip),
            "prefix": str(address),
            "version": version,
            "url": source_link(asset, "ipam/ip-addresses", data.get(field + "_id")),
            "dns_name": dns,
        }
        vrf = data.get(field + "_vrf")
        if isinstance(vrf, dict):
            entry["vrf"] = {
                "name": label(vrf.get("name")),
                "url": source_link(asset, "ipam/vrfs", vrf.get("id")),
            }
        result["addresses"].append(entry)
        if dns and not any(d["name"] == dns for d in result["dns_names"]):
            result["dns_names"].append({"name": dns, "url": entry["url"]})
    if asset.object_type in {"ipam.ipaddress", "ipam.prefix"} and not result["addresses"]:
        raw = data.get("address") or data.get("prefix")
        if isinstance(raw, str):
            result["addresses"].append(
                {
                    "address": raw,
                    "prefix": raw,
                    "url": asset.source_url,
                    "dns_name": label(data.get("dns_name")),
                }
            )
            if data.get("dns_name"):
                result["dns_names"].append({"name": label(data["dns_name"]), "url": asset.source_url})
    return result
