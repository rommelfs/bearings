"""Local Linux seccomp regression: address-family restriction only, not full systemd acceptance.

Requires libseccomp and a built .local/linux-client/bearings-linux-amd64. Collects
local package/interface metadata in memory; no enrollment, delivery or host changes.
"""

import ctypes
import ctypes.util
import errno
import subprocess
import json
import socket
from pathlib import Path

binary = str(Path(__file__).resolve().parents[1] / ".local/linux-client/bearings-linux-amd64")


class Arg(ctypes.Structure):
    _fields_ = [("arg", ctypes.c_uint), ("op", ctypes.c_int), ("a", ctypes.c_uint64), ("b", ctypes.c_uint64)]


def restrict(allowed):
    lib = ctypes.CDLL(ctypes.util.find_library("seccomp"), use_errno=True)
    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_rule_add_array.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.POINTER(Arg),
    ]
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    ctx = lib.seccomp_init(0x7FFF0000)
    # Restrict socket domains to precisely the service's address-family allowlist.
    syscall = lib.seccomp_syscall_resolve_name(b"socket")
    for domain in range(46):
        if domain not in allowed:
            rule = Arg(0, 4, domain, 0)  # EQ
            assert (
                lib.seccomp_rule_add_array(ctx, 0x50000 | errno.EAFNOSUPPORT, syscall, 1, ctypes.byref(rule))
                == 0
            )
    assert lib.seccomp_load(ctx) == 0


for netlink in (False, True):
    allowed = [socket.AF_UNIX, socket.AF_INET, socket.AF_INET6] + ([socket.AF_NETLINK] if netlink else [])
    result = subprocess.run(
        [binary, "collect", "--inventory"],
        preexec_fn=lambda: restrict(allowed),
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    assert ("host" in data) == netlink, (netlink, result.stderr)
    assert bool(data["components"])
    if not netlink:
        assert "network observation unavailable:" in result.stderr
    print(
        "AF_NETLINK", netlink, "host present", "host" in data, "software retained", bool(data["components"])
    )
