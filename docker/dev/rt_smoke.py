"""Real synthetic RT hand-off and lost-ack proof; never target external installations."""

import json
import os
from pathlib import Path
import time
import uuid
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
import httpx

from portal import issues, rt
from portal.models import Asset, AssetIssue, RTInstance, RTTicket
from .smoke import lab_sources


def main():
    root = Path("/run/bearings/secrets")
    config = json.loads((root / "connections.json").read_text())
    if not settings.DEBUG or os.getenv("BEARINGS_RT") != "1" or config["mode"] != "bundled":
        raise RuntimeError("RT write smoke requires the explicitly enabled synthetic bundled lab")
    data = json.loads((root / "rt.json").read_text())
    sources = lab_sources(config)
    source = sources["read_write"]
    item = next(item for item in config["connections"] if item["access_mode"] == "read_write")
    asset = Asset.objects.get(pk=item["assets"][0]["id"], source=source)
    rows = {}
    for kind in ["company", "circl"]:
        instance = RTInstance.objects.get(name="bundled-rt-" + kind)
        if (
            instance.base_url != "https://rt.bearings.test"
            or data["base_url"] != instance.base_url
            or instance.queue_id != data["queues"][kind]
            or not instance.enabled
            or not instance.private_queue_confirmed
            or instance.token_env_var != "RT_BUNDLED_" + kind.upper() + "_TOKEN"
            or instance.organization_id != (source.organization_id if kind == "company" else None)
        ):
            raise RuntimeError("RT destination/queue/policy changed; refusing smoke writes")
        actor = get_user_model().objects.get(
            username="company-admin" if kind == "company" else "circl-analyst", is_active=True
        )
        identity = uuid.uuid5(uuid.NAMESPACE_URL, "bearings:rt-smoke:" + kind + ":" + str(asset.pk))
        issue = AssetIssue.objects.filter(pk=identity).first()
        if issue is None:
            issue = issues.save_issue(
                actor,
                AssetIssue(id=identity, organization=source.organization),
                {
                    "asset": asset,
                    "kind": "support",
                    "title": "SYNTHETIC RT " + kind + " workflow exercise",
                    "source_label": "Synthetic bundled RT exercise",
                    "evidence_text": "Local demonstration only; no real expiry assertion",
                    "shareable": True,
                },
                "Create isolated RT workflow proof",
            )
        before = (issue.status, issue.active)
        row = rt.preview(actor, issue, instance, "SYNTHETIC scoped RT queue and recovery proof")
        if row.state == "draft":
            rt.approve(actor, row.pk)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            rt.process(row.pk)
            row.refresh_from_db()
            if row.state == "linked":
                break
            if row.state == "uncertain":
                # A preceding interrupted smoke can have a real ticket with a lost acknowledgment.
                # Reconcile through the real GET/search API only; never repeat its POST.
                rt.reconcile(row.pk, actor)
                row.refresh_from_db()
                if row.state == "linked":
                    break
            if row.state in {"uncertain", "blocked"}:
                raise RuntimeError("RT creation needs investigation; never blindly repeat a POST")
            time.sleep(1)
        assert row.state == "linked", "RT worker did not confirm the synthetic ticket"
        rt.refresh(row.pk, actor)
        row.refresh_from_db()
        assert row.summary["status"] and row.ticket_url
        expected = row.remote_id
        assert rt.preview(actor, issue, instance, "Ignored repeat").pk == row.pk
        RTTicket.objects.filter(pk=row.pk).update(
            remote_id=None, state="uncertain", last_attempt=timezone.now()
        )
        original = rt.api
        with patch("portal.rt.api", wraps=original) as reads:
            rt.reconcile(row.pk, actor)
            assert reads.call_count > 0 and all(call.args[1] == "GET" for call in reads.call_args_list)
        row.refresh_from_db()
        assert row.remote_id == expected and row.state == "linked"
        issue.refresh_from_db()
        assert (issue.status, issue.active) == before
        rows[kind] = row
    with httpx.Client(
        verify=os.environ["SSL_CERT_FILE"], trust_env=False, follow_redirects=False, timeout=10
    ) as client:
        for kind, row in rows.items():
            foreign = rows["circl" if kind == "company" else "company"]
            headers = {"Authorization": "token " + os.environ[row.instance.token_env_var]}
            assert (
                client.get(
                    row.instance.base_url + f"/REST/2.0/ticket/{row.remote_id}", headers=headers
                ).status_code
                == 200
            )
            response = client.get(
                row.instance.base_url + f"/REST/2.0/ticket/{foreign.remote_id}", headers=headers
            )
            assert response.status_code in {403, 404} and foreign.subject not in response.text
        assert client.get("https://rt.bearings.test/REST/2.0/ticket/1").status_code in {401, 403}
    print(
        "Verified real RT company/CIRCL ticket creation, separate scoped tokens and queues, foreign-ticket denial, retained identities, GET-only lost-ack recovery and status feedback. No issue resolved and no mail delivered externally."
    )
