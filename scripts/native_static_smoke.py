"""Collect actual NetBox static assets from read-only source into a separate directory.

Unprivileged fixture only: no database, host accounts/services or public server.
"""

import argparse
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "deploy/ubuntu24/ecosystem"


def run(args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, capture_output=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--netbox-source", type=Path, required=True)
    args = parser.parse_args()
    if os.getuid() == 0:
        raise SystemExit("Use an unprivileged account so read-only source is enforced")
    revision = run(["git", "-C", args.netbox_source, "rev-parse", "HEAD"], text=True).stdout.strip()
    if revision != "3cd2c1d6469caed6c50e80eddd4cde863e0e2cf5":
        raise SystemExit("Unexpected NetBox fixture revision")
    with tempfile.TemporaryDirectory(prefix="bearings-native-static-") as temporary:
        base = Path(temporary)
        source, destination = base / "source", base / "public-static"
        source.mkdir()
        archive = base / "source.tar"
        with archive.open("wb") as output:
            subprocess.run(
                ["git", "-C", str(args.netbox_source), "archive", "HEAD"], stdout=output, check=True
            )
        with tarfile.open(archive) as tar:
            tar.extractall(source, filter="data")
        venv = base / "venv"
        run(["uv", "venv", "--python", "3.12", venv])
        run(
            [
                "uv",
                "pip",
                "sync",
                "--python",
                venv / "bin/python",
                "--require-hashes",
                TEMPLATES / "netbox-requirements.txt",
            ]
        )
        config = base / "fixture_configuration.py"
        config.write_text(
            "from netbox_configuration import *\n"
            "assert STORAGES['staticfiles']['OPTIONS']['location']=='/var/www/bearings-netbox/static'\n"
            f"STORAGES['staticfiles']['OPTIONS']['location']={str(destination)!r}\n"
        )
        (base / "legacy_configuration.py").write_text(
            f"from fixture_configuration import *\nSTORAGES={{}}\nSTATIC_ROOT={str(destination)!r}\n"
        )
        env = {
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "DJANGO_SETTINGS_MODULE": "netbox.settings",
            "NETBOX_CONFIGURATION": "fixture_configuration",
            "NETBOX_HOST": "netbox.bearings.circl.lu",
            "NETBOX_SECRET_KEY": "synthetic-readonly-static-" + "x" * 64,
            "NETBOX_TOKEN_PEPPER": "synthetic-static-pepper-" + "x" * 64,
            "OIDC_ISSUER": "https://sso.bearings.circl.lu/realms/bearings",
            "OIDC_CLIENT_SECRET": "synthetic-not-operational",
            "PYTHONPATH": f"{base}:{source / 'netbox'}:{TEMPLATES}:{ROOT / 'config'}",
        }
        try:
            for folder, directories, files in os.walk(source):
                Path(folder).chmod(0o555)
                for file in files:
                    path = Path(folder) / file
                    if not path.is_symlink():
                        path.chmod(0o444)
            legacy = subprocess.run(
                [
                    str(venv / "bin/python"),
                    str(source / "netbox/manage.py"),
                    "collectstatic",
                    "--noinput",
                    "--skip-checks",
                ],
                env={**env, "NETBOX_CONFIGURATION": "legacy_configuration"},
                capture_output=True,
            )
            assert legacy.returncode != 0 and b"Permission denied" in legacy.stderr
            assert str(source / "netbox/static").encode() in legacy.stderr
            assert not destination.exists()
            # Verify the effective backend, rather than the ignored config name.
            check = (
                "import django;django.setup();from django.conf import settings;"
                "from django.contrib.staticfiles.storage import staticfiles_storage;"
                f"assert staticfiles_storage.location=={str(destination)!r};"
                f"assert settings.STATIC_ROOT!={str(destination)!r}"
            )
            run([venv / "bin/python", "-c", check], env=env)
            run(
                [
                    venv / "bin/python",
                    source / "netbox/manage.py",
                    "collectstatic",
                    "--noinput",
                    "--skip-checks",
                ],
                env=env,
            )
            assert not (source / "netbox/static").exists()
            css = next(destination.rglob("*.css"))
            assert css.stat().st_mode & 0o777 == 0o644
            assert css.parent.stat().st_mode & 0o777 == 0o755
            print(
                "Native NetBox collectstatic passed with read-only source, separate destination and public asset modes"
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError((error.stderr or b"")[-4000:].decode(errors="replace")) from error
        finally:
            for folder, directories, files in os.walk(source):
                Path(folder).chmod(0o755)


if __name__ == "__main__":
    main()
