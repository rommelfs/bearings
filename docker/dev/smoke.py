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
    sources = {
        i["access_mode"]: NetBoxInstance.objects.get(name=i["name"]).inventorysource_set.get()
        for i in config["connections"]
    }
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
        assert response.status_code == 200 and "Infrastructure overview" in response.text
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
