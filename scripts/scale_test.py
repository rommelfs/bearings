#!/usr/bin/env python3
"""Reproducible synthetic scale test in an owned PostgreSQL container; never uses the dev DB."""

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local/scale-test"
NAME = "bearings-scale-local"
LABEL = "org.bearings.synthetic-scale"


def docker(*args, **kwargs):
    return subprocess.run(["docker", *args], check=True, text=True, **kwargs)


def owned():
    result = docker("inspect", NAME, capture_output=True)
    config = json.loads(result.stdout)[0]
    if config["Config"].get("Labels", {}).get(LABEL) != "1":
        raise SystemExit("Container name is occupied by an unowned container; refusing")
    return config


def private(path, text):
    fd = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)


def environment():
    state_file = LOCAL / "state.json"
    if not state_file.exists():
        raise SystemExit("First run: python3 scripts/scale_test.py seed")
    state = json.loads(state_file.read_text())
    config = owned()
    if not config["State"]["Running"]:
        docker("start", NAME, stdout=subprocess.DEVNULL)
    for _ in range(30):
        check = subprocess.run(
            ["docker", "exec", NAME, "pg_isready", "-U", "bearings_scale"], capture_output=True
        )
        if check.returncode == 0:
            break
        time.sleep(1)
    else:
        raise SystemExit("Isolated PostgreSQL did not become ready")
    config = owned()
    ports = config["NetworkSettings"]["Ports"].get("5432/tcp")
    if ports:
        if ports[0]["HostIp"] != "127.0.0.1":
            raise SystemExit("Scale database must be published on loopback only")
        address, port = "127.0.0.1", int(ports[0]["HostPort"])
    else:
        # Retained Linux-only labs created before loopback publishing was added.
        address = config["NetworkSettings"]["Networks"][NAME]["IPAddress"]
        port = 5432
    env = dict(os.environ)
    # Do not inherit any connector, IdP or SMTP credentials/configuration.
    env = {
        k: v
        for k, v in env.items()
        if not k.startswith(
            ("SMTP_", "OIDC_", "BEARINGS_", "NETBOX_", "MISP_", "FLOWINTEL_", "RT_", "DJANGO_")
        )
    }
    env.update(
        DATABASE_URL=f"postgresql://bearings_scale:{quote(state['password'], safe='')}@{address}:{port}/bearings_scale_local",
        DJANGO_SETTINGS_MODULE="scripts.scale_settings",
        DJANGO_SECRET_KEY=state["secret"],
        BEARINGS_SCALE_TEST="1",
        UV_CACHE_DIR=os.getenv("UV_CACHE_DIR", "/tmp/bearings-uv-cache"),
    )
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["seed", "measure", "workflows", "stop"])
    parser.add_argument("--companies", type=int, default=40000)
    parser.add_argument("--assets-per-company", type=int, default=30)
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()
    if args.action == "stop":
        owned()
        docker("stop", NAME)
        print("Owned scale container stopped; synthetic volume and reports retained.")
        return
    LOCAL.mkdir(parents=True, exist_ok=True)
    if args.action == "seed" and not (LOCAL / "state.json").exists():
        existing = subprocess.run(["docker", "inspect", NAME], capture_output=True)
        if existing.returncode == 0:
            raise SystemExit("Existing container without local ownership state; refusing adoption")
        state = {"password": secrets.token_urlsafe(32), "secret": secrets.token_urlsafe(48)}
        envfile = LOCAL / "postgres.env"
        private(
            envfile,
            f"POSTGRES_USER=bearings_scale\nPOSTGRES_PASSWORD={state['password']}\nPOSTGRES_DB=bearings_scale_local\n",
        )
        docker("network", "create", "--internal", "--label", LABEL + "=1", NAME, stdout=subprocess.DEVNULL)
        docker("volume", "create", "--label", LABEL + "=1", NAME + "-data", stdout=subprocess.DEVNULL)
        docker(
            "run",
            "-d",
            "--name",
            NAME,
            "--label",
            LABEL + "=1",
            "--network",
            NAME,
            "--publish",
            "127.0.0.1::5432",
            "--cpus",
            "2",
            "--memory",
            "3g",
            "--shm-size",
            "512m",
            "--env-file",
            str(envfile),
            "-v",
            NAME + "-data:/var/lib/postgresql/data",
            "postgres:17-alpine",
            "postgres",
            "-c",
            "shared_buffers=256MB",
            "-c",
            "work_mem=16MB",
            "-c",
            "maintenance_work_mem=128MB",
            stdout=subprocess.DEVNULL,
        )
        private(LOCAL / "state.json", json.dumps(state))
    env = environment()
    base = ["uv", "run", "--frozen", "python", "manage.py"]
    if args.action == "seed":
        subprocess.run(
            base + ["migrate", "--noinput"], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL
        )
    subprocess.run(
        base
        + [
            "benchmark_scale",
            args.action,
            "--companies",
            str(args.companies),
            "--assets-per-company",
            str(args.assets_per_company),
            "--label",
            args.label,
            "--samples",
            str(args.samples),
            "--concurrency",
            str(args.concurrency),
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )


if __name__ == "__main__":
    main()
