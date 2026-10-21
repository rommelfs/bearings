"""Isolated RT lab lifecycle. Private inputs never appear in argv or logs."""

import json
import os
from pathlib import Path
import subprocess
import sys

PHASE = "private lab configuration"


def perl(*args):
    return subprocess.run(
        ["perl", "-I/usr/share/request-tracker5/lib", *args], check=True, capture_output=True, text=True
    )


def main():
    global PHASE
    if os.getenv("BEARINGS_RT_LAB") != "1":
        raise RuntimeError("RT bootstrap is restricted to the synthetic bundled lab")
    # Debian's dbconfig snippets must not override the explicit isolated runtime credentials.
    os.environ["RT_SITE_CONFIG_DIR"] = "/run/rt-config/site-config.d"
    Path(os.environ["RT_SITE_CONFIG_DIR"]).mkdir(parents=True, exist_ok=True)
    data = json.loads(Path("/run/rt/config.json").read_text())
    if data["base_url"] != "https://rt.bearings.test":
        raise RuntimeError("Unrecognized RT source identity")
    for root in [Path("/var/lib/request-tracker5"), Path("/var/cache/request-tracker5")]:
        root.mkdir(parents=True, exist_ok=True)
        for name in ["mason_data", "session_data", "log", "data"]:
            (root / name).mkdir(exist_ok=True)
        for path in [root, *root.rglob("*")]:
            os.chown(path, 33, 33, follow_symlinks=False)
    if sys.argv[1] == "init":
        PHASE = "database connection/schema checks"
        probe = perl(
            "-MRT",
            "-e",
            "RT->LoadConfig; RT->ConnectToDatabase; print $RT::Handle->dbh->selectrow_array(q{SELECT to_regclass('public.users')}) // q{};",
        )
        if not probe.stdout.strip():
            PHASE = "fresh RT database initialization"
            subprocess.run(
                [
                    "/usr/sbin/rt-setup-database-5",
                    "--action",
                    "init",
                    "--skip-create",
                    "--root-password-file",
                    "/run/rt/demo_password",
                ],
                check=True,
                capture_output=True,
            )
        rtir_marker = Path("/var/lib/request-tracker5/bearings-rtir.json")
        pending = Path("/var/lib/request-tracker5/.rtir-installing")
        if pending.exists() and pending.read_text() != "provisioning":
            raise RuntimeError(
                "Incomplete RTIR installation requires operator recovery; no automatic reinsertion"
            )
        if os.getenv("BEARINGS_RTIR") == "1" and not rtir_marker.exists() and not pending.exists():
            PHASE = "first RTIR installation (retained RT data preserved)"
            perl(
                "-MRT",
                "-e",
                "RT->LoadConfig; RT->Init; for my $n ('Incidents','Investigations','Incident Reports','Countermeasures') { my $q=RT::Queue->new(RT->SystemUser);$q->Load($n);die 'Existing RTIR queue requires explicit adoption' if $q->Id; }",
            )
            pending.touch(mode=0o600)
            subprocess.run(
                [
                    "/usr/sbin/rt-setup-database-5",
                    "--action",
                    "insert",
                    "--datafile",
                    "/usr/local/share/request-tracker5/plugins/RT-IR/etc/initialdata",
                    "--dba",
                    "rt",
                ],
                check=True,
                capture_output=True,
                env=dict(os.environ, RT_DBA_PASSWORD=Path("/run/rt/db_password").read_text().strip()),
            )
            pending.write_text("provisioning")
        PHASE = "retained account, queue and credential checks"
        perl("/adapter/provision.pl")
        if os.getenv("BEARINGS_RTIR") == "1" or rtir_marker.exists():
            PHASE = "RTIR scoped identities and queue lifecycle checks"
            perl("/adapter/provision_rtir.pl")
            pending.unlink(missing_ok=True)
        print(
            "RT synthetic queues, scoped accounts and retained credentials verified; mail stays in local mbox files."
        )
        return
    if sys.argv[1] == "smoke":
        PHASE = "isolated network, mail and queue permission checks"
        routes = Path("/proc/net/route").read_text().splitlines()[1:]
        if any(row.split()[1] == "00000000" for row in routes):
            raise RuntimeError("RT must remain on the isolated lab network without an Internet route")
        result = perl("/adapter/smoke.pl")
        print(result.stdout.strip())
        return
    config = Path("/run/rt-config")
    PHASE = "Apache/FastCGI and SSO configuration"
    config.mkdir(exist_ok=True)
    source = Path("/adapter/apache.conf").read_text()
    if os.getenv("BEARINGS_RT_SSO") == "1":
        source = source.replace("# SSO_INCLUDE", "Include /run/rt-sso/apache-lab.conf")
        source = "FcgidInitialEnv BEARINGS_RT_SSO 1\n" + source
        overlay = Path("/usr/local/share/request-tracker5/lib/RT/Interface/Web_Local.pm")
        overlay.write_text(Path("/run/rt-sso/Web_Local.pm").read_text())
        overlay.chmod(0o644)
    Path("/etc/apache2/ports.conf").write_text("Listen 443\nListen 444\n")
    # Debian enables another combined log globally; it would retain callback query strings.
    Path("/etc/apache2/conf-enabled/other-vhosts-access-log.conf").unlink(missing_ok=True)
    Path("/etc/apache2/sites-enabled/bearings-rt.conf").write_text(source)
    subprocess.run(["apache2ctl", "configtest"], check=True, capture_output=True)
    os.execv("/usr/sbin/apache2ctl", ["apache2ctl", "-D", "FOREGROUND"])


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, KeyError, OSError, subprocess.CalledProcessError):
        raise SystemExit(
            f"Bundled RT failed during {PHASE}. Inspect private configuration/database health; no credentials or raw provider responses were logged."
        ) from None
