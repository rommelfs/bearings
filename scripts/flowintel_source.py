"""Fetch a reviewed upstream revision into an ignored build context; never overwrite local edits."""

from pathlib import Path
import subprocess
import shutil

REVISION = "0fd54db3d3c7d17c4b26d8759cb6ac857d8d041f"
REPOSITORY = "https://github.com/flowintel/flowintel.git"
ROOT = Path(__file__).resolve().parents[1]


def prepare_source():
    if shutil.which("git") is None:
        raise SystemExit("Git is required to fetch the pinned optional FlowIntel source")
    path = ROOT / ".local/dev-stack/flowintel-source"
    if not path.exists():
        path.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(path)], check=True)
        subprocess.run(["git", "-C", str(path), "remote", "add", "origin", REPOSITORY], check=True)
    if not (path / ".git").is_dir():
        raise SystemExit("FlowIntel build context contains user files; refusing to replace it")
    dirty = subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain"], capture_output=True, text=True, check=True
    ).stdout
    if dirty.strip():
        raise SystemExit("FlowIntel cached source has local changes; preserve/review them before rebuilding")
    current = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--verify", "HEAD"], capture_output=True, text=True
    )
    if current.returncode or current.stdout.strip() != REVISION:
        subprocess.run(["git", "-C", str(path), "fetch", "--depth", "1", REPOSITORY, REVISION], check=True)
        subprocess.run(["git", "-C", str(path), "checkout", "--detach", REVISION], check=True)
    verified = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    if verified != REVISION:
        raise SystemExit("FlowIntel source revision could not be verified")
    return path
