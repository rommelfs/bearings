"""Configure a disabled source and private bundled secret without logging or contacting MISP."""

import getpass
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit
from scripts import dev


def execute(args):
    state = dev.active()
    if state["mode"] != "bundled":
        raise SystemExit(
            "This secret installer supports the bundled lab only; external operators inject their own runtime secret"
        )
    try:
        url = urlsplit(args.url)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.port == 0
            or not re.fullmatch(r"MISP_[A-Z0-9_]*TOKEN", args.credential_ref)
        ):
            raise ValueError()
        token = (
            Path(args.token_file).read_text()
            if args.token_file
            else getpass.getpass("MISP read API key (hidden): ")
        )
        token = token.strip()
        if not token or len(token) > 4096 or "\n" in token or "\r" in token:
            raise ValueError()
    except (ValueError, OSError):
        raise SystemExit(
            "Use an approved HTTPS URL, MISP_*TOKEN reference and a nonempty single-line private key"
        ) from None
    base = dev.compose(
        state["mode"],
        state["project"],
        state.get("flowintel", False),
        state.get("sso", False),
        state.get("rt", False),
        state.get("rtir", False),
    )
    try:
        result = dev.run(
            base
            + [
                "exec",
                "-T",
                "web",
                "/app/.venv/bin/python",
                "docker/dev/entrypoint.py",
                "manage",
                "configure_misp",
                "--actor",
                args.actor,
            ],
            input=json.dumps(
                {
                    "name": args.name,
                    "base_url": args.url.rstrip("/"),
                    "token_env_var": args.credential_ref,
                    "allow_private": args.allow_private,
                }
            ),
            capture_output=True,
            text=True,
        )
        source_id = json.loads(result.stdout)["source"]
        code = """import json,os,secrets,sys
from pathlib import Path
value=json.load(sys.stdin)
root=Path('/run/bearings/secrets')
name=value['name']
import re
assert re.fullmatch(r'MISP_[A-Z0-9_]*TOKEN',name)
path=root/('.misp-'+secrets.token_hex(16))
fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
with os.fdopen(fd,'w') as handle:
 handle.write(value['token'])
 handle.flush()
 os.fsync(handle.fileno())
os.chown(path,int((root/'app_uid').read_text()),0)
os.replace(path,root/name)
"""
        dev.run(
            base
            + [
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "--entrypoint",
                "/opt/netbox/venv/bin/python",
                "netbox-provision",
                "-c",
                code,
            ],
            input=json.dumps({"name": args.credential_ref, "token": token}),
            capture_output=True,
            text=True,
        )
        dev.run(base + ["restart", "web", "worker"], capture_output=True, text=True)
    except (subprocess.CalledProcessError, ValueError, KeyError):
        raise SystemExit(
            "MISP configuration is incomplete or refused; no source was enabled by this command. Review current source state. No key or upstream body was logged."
        ) from None
    print(
        f"MISP source {source_id} configured and disabled; private key installed. No upstream request made."
    )
    print("Review the source in Bearings administration, then explicitly enable it for background reads.")
