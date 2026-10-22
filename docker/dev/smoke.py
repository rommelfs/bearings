"""Live, synthetic bundled-stack verification. Never writes to an external configuration."""

import json
import os
import time
import uuid
from pathlib import Path
import httpx
from django.conf import settings
from django.utils import timezone
from portal.models import Asset, InventoryWrite, NetBoxInstance
from portal.services import query_inventory
from portal.inventory import refresh_inventory


def lab_sources(config):
    sources = {}
    for item in config["connections"]:
        instance = NetBoxInstance.objects.get(name=item["name"])
        source = instance.inventorysource_set.get()
        if (
            instance.base_url != "https://netbox.bearings.test"
            or instance.token_env_var != item["token_env_var"]
            or instance.auth_scheme != "Bearer"
            or instance.access_mode != item["access_mode"]
            or not instance.enabled
            or source.mode != "central"
            or source.tenant_id != item["tenant_id"]
            or source.organization.slug != item["organization_slug"]
        ):
            raise RuntimeError("Lab connection changed; refusing smoke queries or writes")
        sources[item["access_mode"]] = source
    if set(sources) != {"read_only", "read_write"}:
        raise RuntimeError("Both expected lab capabilities are required")
    return sources


def main():
    root = Path("/run/bearings")
    config = json.loads((root / "secrets/connections.json").read_text())
    if not settings.DEBUG or os.getenv("BEARINGS_DEV_STACK") != "1" or config["mode"] != "bundled":
        raise RuntimeError("Write smoke tests are restricted to the bundled synthetic lab")
    if any(
        c["base_url"] != "https://netbox.bearings.test" or not c["name"].startswith("bundled-netbox-")
        for c in config["connections"]
    ):
        raise RuntimeError("Unexpected target; refusing writes")
    password = (root / "secrets/demo_password").read_text().strip()
    sources = lab_sources(config)
    for source in sources.values():
        rows = query_inventory(source, ["devices", "virtual-machines", "ip-addresses", "prefixes"])
        assert all(rows.values()), "Expected synthetic inventory from every endpoint"
    ro = sources["read_only"]
    rw = sources["read_write"]
    token = os.environ[ro.instance.token_env_var]
    with httpx.Client(verify=os.environ["SSL_CERT_FILE"], trust_env=False, follow_redirects=False) as netbox:
        response = netbox.post(
            "https://netbox.bearings.test/api/dcim/devices/",
            headers={"Authorization": "Bearer " + token},
            json={"name": "must-not-be-created"},
        )
        assert response.status_code == 403, "Upstream read-only token must reject POST"
        response = netbox.get("https://netbox.bearings.test/login/")
        assert response.status_code == 200
        response = netbox.post(
            "https://netbox.bearings.test/login/",
            data={
                "username": "netbox-admin",
                "password": password,
                "csrfmiddlewaretoken": netbox.cookies.get("netboxcsrftoken"),
            },
            headers={"Referer": "https://netbox.bearings.test/login/"},
        )
        assert response.status_code == 302, "Bundled NetBox admin login failed"
        # Create directly in NetBox, without a bearings_id or starter fixture identity.
        api_headers = {
            "X-CSRFToken": netbox.cookies.get("netboxcsrftoken"),
            "Referer": "https://netbox.bearings.test/",
        }
        name = "smoke-import-" + uuid.uuid4().hex[:8]
        response = netbox.post(
            "https://netbox.bearings.test/api/dcim/devices/",
            headers=api_headers,
            json={
                "name": name,
                "status": "active",
                "site": rw.instance.site_id,
                "role": rw.instance.role_id,
                "device_type": rw.instance.device_type_id,
                "tenant": rw.tenant_id,
            },
        )
        assert response.status_code == 201, "Direct synthetic NetBox creation failed"
        external_id = str(response.json()["id"])
        refresh_inventory(rw.pk)
        imported = Asset.objects.get(source=rw, object_type="dcim.device", external_id=external_id)
        assert imported.source_url.startswith("https://localhost:"), (
            "Bundled browser links must use the host gateway port"
        )
        imported.criticality, imported.responsible_team = "high", "local smoke review"
        imported.save()
        endpoint = "https://netbox.bearings.test/api/dcim/devices/" + external_id + "/"
        response = netbox.patch(endpoint, headers=api_headers, json={"name": name + "-updated"})
        assert response.status_code == 200
        refresh_inventory(rw.pk)
        imported.refresh_from_db()
        assert (
            imported.name == name + "-updated"
            and imported.criticality == "high"
            and imported.responsible_team == "local smoke review"
        )
        # Only remove the synthetic probe created by this invocation; retain its local projection.
        assert netbox.delete(endpoint, headers=api_headers).status_code == 204
        refresh_inventory(rw.pk)
        imported.refresh_from_db()
        assert imported.missing_since is not None and imported.criticality == "high"
        refresh_inventory(ro.pk)
        for item in config["connections"]:
            source = sources[item["access_mode"]]
            for seed in item["assets"]:
                asset = Asset.objects.get(source=source, pk=seed["id"])
                data = asset.upstream_data
                assert data.get("primary_ip4") and data.get("primary_ip6")
                assert data.get("primary_ip4_dns_name", "").endswith(".example.invalid")
                assert data.get("primary_ip6_dns_name") == data["primary_ip4_dns_name"]
                assert data.get("platform", {}).get("name") == "Debian 12 (SYNTHETIC)"
                if seed["kind"] == "server":
                    assert data.get("rack") and data.get("location") and data.get("position") == "10"
                    assert data.get("serial", "").startswith("SYNTHETIC-") and data.get("asset_tag")
        print(
            "Verified real primary IPv4/IPv6, DNS/platform and physical room/rack/U/serial/tag for all four bundled starter assets."
        )
        assert not ro.asset_set.filter(pk=imported.pk).exists()
        assert (
            Asset.objects.filter(source=rw, object_type="dcim.device", external_id=external_id).count() == 1
        )
        print(
            "Verified general import from direct NetBox creation, update, local assessment preservation and retained missing object; read-only import passed."
        )
    print("Verified HTTPS, both scoped keys, four query types, upstream read-only denial and NetBox login.")
    base = "http://127.0.0.1:8000"
    with httpx.Client(trust_env=False, follow_redirects=True) as client:
        client.get(base + "/accounts/login/")
        response = client.post(
            base + "/accounts/login/",
            data={
                "username": "company-admin",
                "password": password,
                "csrfmiddlewaretoken": client.cookies.get("csrftoken"),
            },
        )
        assert response.status_code == 200 and response.url.path == "/", "Bearings login failed"
        assert "<h1>Vulnerability review</h1>" in response.text and "company-admin" in response.text
        assert 'id="review-heading"' in response.text and 'class="severity-filters"' in response.text
        located = rw.asset_set.filter(
            object_type="dcim.device", state="synced", missing_since__isnull=True
        ).first()
        detail = client.get(base + f"/organizations/{rw.organization.slug}/assets/{located.pk}/")
        assert detail.status_code == 200 and "Locate this machine" in detail.text
        assert located.name in detail.text and located.source_url in detail.text
        ro_url = base + f"/organizations/{ro.organization.slug}/assets/new/"
        fields = {
            "name": "must-not-be-created",
            "kind": "server",
            "criticality": "normal",
            "lifecycle": "active",
            "csrfmiddlewaretoken": client.cookies.get("csrftoken"),
        }
        assert client.post(ro_url, data=fields).status_code == 403, "Portal must reject read-only writes"
        for kind in ["server", "vm"]:
            name = "smoke-" + kind + "-" + uuid.uuid4().hex[:8]
            fields.update(
                {"name": name, "kind": kind, "csrfmiddlewaretoken": client.cookies.get("csrftoken")}
            )
            response = client.post(base + f"/organizations/{rw.organization.slug}/assets/new/", data=fields)
            assert response.status_code == 200, "Portal submission failed"
            asset = Asset.objects.get(source=rw, name=name)
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                asset.refresh_from_db()
                if asset.state in {"synced", "failed"}:
                    break
                time.sleep(1)
            assert asset.state == "synced", f"{kind} worker write was not confirmed"
            saved_id = asset.external_id
            # Recreate the local state of an accepted POST whose acknowledgement was lost.
            job = asset.write
            InventoryWrite.objects.filter(pk=job.pk).update(completed_at=None, next_attempt=timezone.now())
            Asset.objects.filter(pk=asset.pk).update(state="pending", external_id="")
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                asset.refresh_from_db()
                if asset.state in {"synced", "failed"}:
                    break
                time.sleep(1)
            assert asset.state == "synced" and asset.external_id == saved_id, (
                "Write recovery changed identity"
            )
            rows = query_inventory(rw, ["devices" if kind == "server" else "virtual-machines"])
            matches = [
                r
                for group in rows.values()
                for r in group
                if r["record"].get("custom_fields", {}).get("bearings_id") == str(asset.pk)
            ]
            assert len(matches) == 1, "Write recovery duplicated an upstream object"
        print(
            "Verified Bearings login, portal read-only denial, worker device/VM writes and lost-ack recovery without duplicates."
        )
