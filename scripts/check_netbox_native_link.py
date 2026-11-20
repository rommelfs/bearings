"""Run the actual native link script only against the guarded bundled NetBox lab."""

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
prefix = """
import os,sys
assert os.environ.get('DB_HOST') == 'netbox-db'
assert os.environ.get('BEARINGS_NETBOX_BROWSER_URL','').startswith('https://localhost:')
import bearings_oidc
sys.modules['oidc']=bearings_oidc
"""
source = (ROOT / "deploy/ubuntu24/ecosystem/netbox_link.py").read_text()
checks = (ROOT / "scripts/netbox_native_link_checks.py").read_text()
program = prefix + "\nNATIVE_LINK_SOURCE=" + repr(source) + "\n" + checks
subprocess.run(
    [
        "docker",
        "exec",
        "-i",
        "bearings-dev-netbox-1",
        "/opt/netbox/venv/bin/python",
        "/opt/netbox/netbox/manage.py",
        "shell",
        "--no-startup",
        "--no-imports",
        "-c",
        "import sys;exec(sys.stdin.read())",
    ],
    input=program,
    text=True,
    check=True,
)
