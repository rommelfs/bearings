"""Fetch the pinned public RTIR source; never install from an unverified archive."""

import hashlib
import os
from pathlib import Path
import ssl
import subprocess
import tarfile
import urllib.request

url = "https://download.bestpractical.com/pub/rt/release/RT-IR-5.0.10.tar.gz"
context = ssl.create_default_context()
if Path("/run/secrets/cloud-ca").exists():
    context.load_verify_locations("/run/secrets/cloud-ca")


def fetch(url, digest, filename, destination):
    with urllib.request.urlopen(url, context=context, timeout=60) as response:
        archive = response.read(4 * 1024 * 1024)
    if hashlib.sha256(archive).hexdigest() != digest:
        raise SystemExit("Public source digest mismatch")
    Path(filename).write_bytes(archive)
    with tarfile.open(filename) as source:
        source.extractall(destination, filter="data")


fetch(
    "https://cpan.metacpan.org/authors/id/B/BP/BPS/Parse-BooleanLogic-0.10.tar.gz",
    "66f0340ce651090f48a73ae49168444455d6e9f58b449decc3810c02ff9b48b6",
    "/tmp/boolean.tar.gz",
    "/tmp/rtir-source",
)
subprocess.run(
    ["sh", "-ec", "perl Makefile.PL && make && make install"],
    cwd="/tmp/rtir-source/Parse-BooleanLogic-0.10",
    check=True,
)
fetch(
    url,
    "b99d35e5e7730ce1ac99719b995a5e6756993986b3f90b8748867a9e68fcbd55",
    "/tmp/rtir.tar.gz",
    "/tmp/rtir-source",
)
os.chdir("/tmp/rtir-source/RT-IR-5.0.10")
os.environ["RTHOME"] = "/usr/share/request-tracker5"
os.execvp("sh", ["sh", "-ec", "perl Makefile.PL </dev/null && make && make install"])
