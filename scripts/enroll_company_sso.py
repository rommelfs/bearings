"""Explicit, read-only-by-default local operator plan; no production/external provisioning."""

import json
import subprocess
from scripts import dev


def execute(args):
    state = dev.active()
    if state["mode"] != "bundled" or not state.get("sso"):
        raise SystemExit(
            "Company provisioning requires the explicit bundled SSO lab. External IdPs/NetBox remain operator-managed."
        )
    base = dev.compose(
        state["mode"],
        state["project"],
        state.get("flowintel", False),
        True,
        state.get("rt", False),
        state.get("rtir", False),
    )
    command = base + [
        "exec",
        "-T",
        "web",
        "/app/.venv/bin/python",
        "docker/dev/entrypoint.py",
        "manage",
        "company_sso_plan",
        "--actor",
        args.actor,
        "--username",
        args.username,
    ]
    if args.without_netbox:
        command.append("--without-netbox")
    try:
        original = json.loads(dev.run(command, capture_output=True, text=True).stdout)
    except (subprocess.CalledProcessError, ValueError):
        raise SystemExit(
            "Company SSO plan refused. Check active platform actor, approved owner/registration and source. Nonempty manual inventory requires reviewed migration; --without-netbox leaves it unchanged."
        ) from None
    print("Company: " + json.dumps(original["company_name"], ensure_ascii=True))
    print("Owner: " + json.dumps(original["username"], ensure_ascii=True))
    print("Identity provider: " + original["issuer"])
    print(
        "NetBox: "
        + (
            "new company tenant with own inventory view/add/change; no global role"
            if original["netbox"]
            else "unchanged (SSO only)"
        )
    )
    print("Plan fingerprint: " + original["fingerprint"])
    if not args.apply:
        print(
            "Plan only. Add --apply to provision this approved local-lab company. No accounts or policies changed."
        )
        return

    def stage(service, script, data, netbox=False):
        target = "/company-enroll.py"
        invocation = base + [
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "--entrypoint",
            "/opt/netbox/venv/bin/python" if netbox else "/app/.venv/bin/python",
            "-v",
            str(dev.ROOT / "docker/sso" / script) + ":" + target + ":ro",
            service,
        ]
        if netbox:
            code = "exec(open('/company-enroll.py').read()); import sys\ntry:\n print('SSO_RESULT:' + json.dumps(main(json.load(sys.stdin))))\nexcept Exception as error:\n raise SystemExit('Native company enrollment refused: ' + type(error).__name__) from None"
            invocation += [
                "/opt/netbox/netbox/manage.py",
                "shell",
                "--no-startup",
                "--no-imports",
                "-c",
                code,
            ]
        else:
            invocation += [target]
        result = dev.run(invocation, input=json.dumps(data), capture_output=True, text=True)
        lines = [
            line[len("SSO_RESULT:") :]
            for line in result.stdout.splitlines()
            if line.startswith("SSO_RESULT:")
        ]
        if len(lines) != 1:
            raise ValueError("Stage did not produce one result")
        return json.loads(lines[0])

    try:
        directory = dev.LOCAL / "company-sso"
        cache = directory / (original["registration"] + ".json")
        identity_request = dict(original)
        if cache.exists():
            receipt = json.loads(cache.read_text())
            if (
                receipt.get("registration") != original["registration"]
                or receipt.get("issuer") != original["issuer"]
            ):
                raise ValueError("Operator identity receipt does not match")
            identity_request["managed_subject"] = receipt["subject"]
        idp = stage("bearings-sso-provision", "enroll_keycloak.py", identity_request)
        if idp.get("initial_password"):
            directory.mkdir(exist_ok=True, parents=True)
            dev.private_file(cache, json.dumps(idp))
        native = (
            stage(
                "netbox-provision",
                "enroll_netbox.py",
                {**original, "subject": idp["subject"], "phase": "prepare"},
                True,
            )
            if original["netbox"]
            else None
        )
        if native:
            # Load the newly isolated token before making the source visible to workers.
            dev.run(base + ["restart", "web", "worker"], capture_output=True, text=True)
        final = json.loads(
            dev.run(
                command + ["--finalize"],
                input=json.dumps(
                    {
                        "original": original,
                        "idp": {"issuer": idp["issuer"], "subject": idp["subject"]},
                        "native": native,
                    }
                ),
                capture_output=True,
                text=True,
            ).stdout
        )
        if native:
            stage(
                "netbox-provision",
                "enroll_netbox.py",
                {**original, "subject": idp["subject"], "phase": "identity"},
                True,
            )
    except (subprocess.CalledProcessError, ValueError, OSError):
        raise SystemExit(
            "Company provisioning is incomplete/refused; no existing account passwords or disabled grants were reset. Retry the reviewed command; owned stage identities are retained. Inspect local operator stages without publishing secret output."
        ) from None
    print("SSO ready. Bearings owner/roles and local recovery password preserved.")
    print("SSO username: " + json.dumps(idp["username"], ensure_ascii=True))
    if native:
        print(
            "NetBox: "
            + native["browser_url"]
            + "/login/ — choose OpenID Connect; tenant "
            + str(native["tenant"])
        )
    if cache.exists():
        saved = json.loads(cache.read_text())
        if saved["subject"] == idp["subject"]:
            print(
                "Initial temporary IdP password (must change at the provider; it may already have been changed):",
                flush=True,
            )
            print(saved["initial_password"], flush=True)
    else:
        print("Use the existing IdP password. No existing password was read/reset.")
    print(
        "Company identity: " + final["registration"] + ". Share credentials only through a trusted channel."
    )
