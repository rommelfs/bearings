"""SMTP relay syntax, independent of Django initialization."""

import ipaddress
import re


def relay_hostname(value):
    value = value.strip()
    if not value:
        return ""
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass
    if len(value) > 253 or not all(
        re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
        for label in value.rstrip(".").split(".")
    ):
        raise ValueError("SMTP_HOST requires a hostname or bracketed relay; set its port separately")
    return value
