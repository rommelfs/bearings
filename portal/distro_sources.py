"""Immutable public vendor destinations; no company inventory or version is sent upstream."""

import bz2
import hashlib
import time
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import httpx
from django.conf import settings
from .connectors.http import ConnectorError, approved_base

UBUNTU = {"20.04": "focal", "22.04": "jammy", "24.04": "noble", "26.04": "resolute"}
DEBIAN = {"11": "bullseye", "12": "bookworm", "13": "trixie"}


def key_for(os):
    distro = os.get("id")
    version = os.get("version", "")
    if distro == "ubuntu" and version in UBUNTU:
        return "ubuntu:" + version
    if distro == "debian" and version.split(".")[0] in DEBIAN:
        return "debian:" + version.split(".")[0]
    if distro == "rhel" and version.split(".")[0] in {"8", "9", "10"}:
        return "rhel:" + version.split(".")[0]
    return None


def url_for(key):
    distro, release = key.split(":")
    if distro == "ubuntu" and release in UBUNTU:
        return f"https://security-metadata.canonical.com/oval/com.ubuntu.{UBUNTU[release]}.cve.oval.xml.bz2"
    if distro == "debian" and release in DEBIAN:
        return f"https://www.debian.org/security/oval/oval-definitions-{DEBIAN[release]}.xml.bz2"
    if distro == "rhel" and release in {"8", "9", "10"}:
        return f"https://security.access.redhat.com/data/oval/v2/RHEL{release}/rhel-{release}.oval.xml.bz2"
    raise ConnectorError("Unsupported distribution release")


@contextmanager
def download(key):
    url = url_for(key)
    approved_base(url, proxy_dns=settings.CONNECTOR_PROXY_DNS)
    with TemporaryDirectory(prefix="bearings-oval-") as tmp:
        path = Path(tmp) / "feed.xml"
        decoder = bz2.BZ2Decompressor()
        compressed = expanded = 0
        h = hashlib.sha256()
        deadline = time.monotonic() + 120
        try:
            with path.open("wb") as out, httpx.Client(timeout=20, follow_redirects=False) as client:
                with client.stream("GET", url, headers={"Accept-Encoding": "identity"}) as response:
                    if response.status_code != 200:
                        raise ConnectorError(
                            f"Vendor HTTP {response.status_code}; last complete cache retained"
                        )
                    if response.headers.get("content-encoding", "identity") not in {"identity", ""}:
                        raise ConnectorError("Unexpected HTTP content encoding")
                    for chunk in response.iter_bytes(65536):
                        compressed += len(chunk)
                        h.update(chunk)
                        if compressed > 32 * 1024 * 1024 or time.monotonic() > deadline:
                            raise ConnectorError("Compressed feed size/time limit exceeded")
                        data = decoder.decompress(chunk, max_length=1024 * 1024)
                        while True:
                            expanded += len(data)
                            if expanded > 384 * 1024 * 1024:
                                raise ConnectorError("Expanded feed limit exceeded")
                            out.write(data)
                            if decoder.eof:
                                if decoder.unused_data:
                                    raise ConnectorError("Trailing compressed input")
                                break
                            if decoder.needs_input:
                                break
                            data = decoder.decompress(b"", max_length=1024 * 1024)
                    if not decoder.eof or expanded < 100:
                        raise ConnectorError("Incomplete compressed vendor feed")
        except (httpx.HTTPError, OSError, EOFError, ValueError) as exc:
            raise ConnectorError(
                "Verified vendor feed transport/decompression failed; cache retained"
            ) from exc
        yield path, h.hexdigest()
