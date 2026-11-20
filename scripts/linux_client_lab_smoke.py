#!/usr/bin/env python3
"""Actual client -> local TLS ingress -> scoped NetBox VM creation; explicitly retained synthetic fixture only."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from scripts import dev

    state = dev.active()
    if state["mode"] != "bundled" or not state["sso"]:
        raise SystemExit(
            "This acceptance requires the retained bundled HTTPS lab; external destinations are refused"
        )
    client = ROOT / ".local/linux-client/bearings-linux-amd64"
    ca = ROOT / ".local/dev-stack/netbox-ca.crt"
    if not client.is_file() or not ca.is_file():
        raise SystemExit("Build the Linux client and start the bundled HTTPS lab first")
    base = dev.compose(
        state["mode"], state["project"], state["flowintel"], state["sso"], state["rt"], state["rtir"]
    )

    def server(code):
        prefix = ""
        result = subprocess.run(
            base
            + [
                "exec",
                "-T",
                "web",
                "/app/.venv/bin/python",
                "docker/dev/entrypoint.py",
                "manage",
                "shell",
                "--no-imports",
                "-v",
                "0",
                "-c",
                prefix + code,
            ],
            cwd=ROOT,
            env=dev.environment(),
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError("Bundled server validation failed; no credentials or response were printed")
        return json.loads(result.stdout)

    hostname = "synthetic-bearings-linux-" + uuid.uuid4().hex[:8]
    with tempfile.TemporaryDirectory(prefix="bearings-linux-lab-") as directory:
        directory = Path(directory)
        container = [
            "docker",
            "run",
            "-i",
            "--rm",
            "--network",
            "host",
            "--hostname",
            hostname,
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory",
            "192m",
            "--cpus",
            "1",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-v",
            f"{client}:/bearings-linux:ro",
            "-v",
            f"{ca}:/ca.pem:ro",
            "-v",
            f"{directory}:/state",
            "rockylinux:9-minimal",
            "/bearings-linux",
        ]

        def run(command, *args, stdin=None):
            result = subprocess.run(
                container + [command, "--state-dir", "/state/client", *args],
                capture_output=True,
                input=stdin,
                text=True,
                timeout=40,
            )
            if result.returncode:
                raise RuntimeError("Native client lab step failed; no credentials or response were printed")
            return json.loads(result.stdout.strip()) if result.stdout.strip() else None

        public = run("init")["public_key"]
        result = server(
            "import json; from pathlib import Path; from django.conf import settings; from docker.dev.smoke import lab_sources; from portal import agents; "
            "assert settings.DEBUG; config=json.loads(Path('/run/bearings/secrets/connections.json').read_text()); assert config['mode']=='bundled'; "
            "source=lab_sources(config)['read_write']; actor=source.organization.membership_set.select_related('user').filter(role='admin',user__is_active=True).order_by('pk').first().user; "
            f"grant,token=agents.create_enrollment(actor,source.organization,None,{public!r},new_asset_kind='vm'); "
            "print(json.dumps({'schema':'bearings.agent.grant.v1','url':'https://localhost:9441','grant':token,'public_key':grant.public_key,'asset_id':'','register_host':True,'expires_at':grant.expires_at.isoformat()}))"
        )
        grant_path = directory / "grant.json"
        grant_path.write_text(json.dumps(result))
        grant_path.chmod(0o600)
        try:
            response = run(
                "enroll", "--grant-file", "/state/grant.json", "--ca-file", "/ca.pem", "--register-host"
            )
            device_id = response["device_id"]
            receipt = run("report", "--package", "bash")
            checked = server(
                "import json; from pathlib import Path; from django.conf import settings; from docker.dev.smoke import lab_sources; from portal import agents; from portal.models import AgentDevice,AgentEnrollment,InventoryWrite; from portal.services import process_write; from portal.connectors.netbox import write_asset; "
                "assert settings.DEBUG; config=json.loads(Path('/run/bearings/secrets/connections.json').read_text()); source=lab_sources(config)['read_write']; "
                f"device=AgentDevice.objects.select_related('asset','source','organization').get(pk={device_id!r},source=source); assert device.asset.name=={hostname!r}; "
                "proof=AgentEnrollment.objects.get(device_id=device.pk); assert proof.signed_body and proof.signature and proof.request_url=='https://localhost:9441/api/v1/agent/enroll/'; "
                "job=InventoryWrite.objects.get(asset=device.asset); process_write(job.pk,force=True); device.asset.refresh_from_db(); assert device.asset.state=='synced'; "
                "kind,remote=write_asset(device.asset); assert kind=='virtualization.virtualmachine' and remote==device.asset.external_id; "
                f"agents.process_one(device.pk,{receipt['report_id']!r}); assert device.reports.get(pk={receipt['report_id']!r}).status=='applied'; "
                "assert device.components.get().name=='bash'; actor=source.organization.membership_set.select_related('user').filter(role='admin',user__is_active=True).order_by('pk').first().user; "
                "agents.revoke(actor,source.organization,device.pk); "
                "print(json.dumps({'tls_verified':True,'native_rpm_client':True,'source_tenant_verified':True,'netbox_vm_created_and_reconciled':True,'exact_report_applied':True,'credential_revoked':True,'asset_id':str(device.asset_id),'retained_synthetic_fixture':True}))"
            )
            print(json.dumps(checked))
        finally:
            # Cancel the grant even if enrollment succeeded but its acknowledgment was lost.
            grant_id = str(uuid.UUID(result["grant"].split(".", 1)[0]))
            server(
                "import json; from portal import agents; from portal.models import AgentEnrollment; "
                f"g=AgentEnrollment.objects.select_related('organization','created_by').get(pk={grant_id!r}); "
                "agents.cancel_enrollment(g.created_by,g.organization,g.pk); print(json.dumps({'cancelled':True}))"
            )
        # A separate key on the actual client bootstraps against the read-only native source.
        run("init", "--state-dir", "/state/fleet")
        rollout = server(
            "import json; from pathlib import Path; from django.conf import settings; from django.contrib.auth import get_user_model; from docker.dev.smoke import lab_sources; from portal import agent_fleets; "
            "assert settings.DEBUG; config=json.loads(Path('/run/bearings/secrets/connections.json').read_text()); assert config['mode']=='bundled'; "
            "source=lab_sources(config)['read_only']; assert not source.can_write; actor=get_user_model().objects.filter(is_superuser=True,is_active=True).order_by('pk').first(); "
            "fleet,token=agent_fleets.create(actor,source.organization,'SYNTHETIC client rollout','server',1,1); print(json.dumps({'id':str(fleet.pk),'token':token}))"
        )
        try:
            enrolled = run(
                "bootstrap",
                "--state-dir",
                "/state/fleet",
                "--server",
                "https://localhost:9441",
                "--ca-file",
                "/ca.pem",
                stdin=rollout["token"],
            )
            again = run(
                "bootstrap", "--state-dir", "/state/fleet", "--server", "https://localhost:9441", stdin=""
            )
            assert again["device_id"] == enrolled["device_id"]
            receipt = run("report", "--state-dir", "/state/fleet", "--package", "bash")
            checked = server(
                "import json; from portal import agents; from portal.inventory import refresh_inventory; from portal.models import AgentDevice,InventoryWrite,AgentFleet; "
                f"d=AgentDevice.objects.select_related('asset','source__instance','organization').get(pk={enrolled['device_id']!r}); "
                "assert not d.source.can_write and d.asset.state=='recorded' and d.asset.object_type=='bearings.agent_host' and not d.asset.external_id; "
                "assert d.asset.upstream_data['agent_observed_only'] and not InventoryWrite.objects.filter(asset=d.asset).exists(); "
                "refresh_inventory(d.source_id); d.asset.refresh_from_db(); assert d.asset.missing_since is None and d.asset.state=='recorded' and d.asset.upstream_data['agent_observed_only']; "
                f"agents.process_one(d.pk,{receipt['report_id']!r}); assert d.components.get().name=='bash'; "
                f"assert AgentFleet.objects.get(pk={rollout['id']!r}).issued_devices==1; "
                "print(json.dumps({'synthetic_fleet_bootstrap':True,'native_tls':True,'read_only_source_retained':True,'no_netbox_write_queued':True,'retry_same_device':True,'report_applied':True}))"
            )
            print(json.dumps(checked))
        finally:
            server(
                "import json; from portal import agent_fleets,agents; from portal.models import AgentFleet,AgentFleetRegistration; "
                f"f=AgentFleet.objects.select_related('organization','created_by').get(pk={rollout['id']!r}); "
                "agent_fleets.revoke(f.created_by,f.organization,f.pk); "
                "[agents.cancel_enrollment(f.created_by,f.organization,r.enrollment_id) for r in AgentFleetRegistration.objects.filter(fleet=f)]; print(json.dumps({'revoked':True}))"
            )
    print("Retained only the explicitly named SYNTHETIC fixture; temporary client key and grant removed.")


if __name__ == "__main__":
    main()
