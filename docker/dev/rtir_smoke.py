"""Native RTIR Incidents with scoped Investigations across two companies, isolated lab only."""

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
    if not settings.DEBUG or os.getenv("BEARINGS_RTIR") != "1" or config["mode"] != "bundled":
        raise RuntimeError("RTIR smoke requires the explicitly enabled synthetic bundled lab")
    native = json.loads((root / "rtir.json").read_text())
    instance = RTInstance.objects.get(name="bundled-rtir-circl")
    if (
        instance.base_url != "https://rt.bearings.test"
        or instance.organization_id
        or instance.product != "rtir"
        or instance.token_env_var != "RT_BUNDLED_RTIR_TOKEN"
        or instance.queue_id != native["queues"]["investigation"]
        or instance.incident_queue_id != native["queues"]["incident"]
        or not instance.enabled
        or not instance.private_queue_confirmed
    ):
        raise RuntimeError("RTIR source/identity/queue/policy changed; no smoke writes permitted")
    source = lab_sources(config)["read_write"]
    item = next(item for item in config["connections"] if item["access_mode"] == "read_write")
    assets = [Asset.objects.get(pk=entry["id"], source=source) for entry in item["assets"][:2]]
    if len(assets) != 2:
        raise RuntimeError("Two synthetic NetBox assets required")
    # Retain the original two RW asset bindings and add one asset from the separate RO company.
    ro_source = lab_sources(config)["read_only"]
    ro_item = next(item for item in config["connections"] if item["access_mode"] == "read_only")
    assets.append(Asset.objects.get(pk=ro_item["assets"][0]["id"], source=ro_source))
    actor = get_user_model().objects.get(username="circl-analyst", is_active=True)
    issue_rows = []
    for asset in assets:
        marker = uuid.uuid5(uuid.NAMESPACE_URL, "bearings:rtir-smoke:" + str(asset.pk))
        issue = AssetIssue.objects.filter(pk=marker).first()
        if not issue:
            issue = issues.save_issue(
                actor,
                AssetIssue(id=marker, organization=asset.organization),
                {
                    "asset": asset,
                    "kind": "support",
                    "title": "SYNTHETIC coordinated RTIR investigation",
                    "source_label": "Synthetic RTIR exercise",
                    "evidence_text": "Local workflow example only; no real incident or expiry assertion",
                    "shareable": True,
                },
                "Create isolated RTIR example",
            )
        if (
            issue.asset_id != asset.pk
            or issue.organization_id != asset.organization_id
            or not issue.shareable
        ):
            raise RuntimeError("RTIR synthetic evidence identity/policy changed")
        issue_rows.append(issue)

    def link(issue, incident=None):
        row = rt.preview(actor, issue, instance, "SYNTHETIC explicit RTIR coordination proof", incident)
        if row.state == "draft":
            rt.approve(actor, row.pk)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            rt.process(row.pk)
            row.refresh_from_db()
            if row.state == "uncertain":
                rt.reconcile(row.pk, actor)
                row.refresh_from_db()
            if row.state == "linked":
                rt.refresh(row.pk, actor)
                return rt.load(row.pk)
            if row.state in {"blocked", "uncertain"}:
                raise RuntimeError("RTIR creation needs operator review; no repeat POST")
            time.sleep(1)
        raise RuntimeError("RTIR worker did not confirm synthetic ticket")

    before = [(issue.status, issue.active) for issue in issue_rows]
    parent = link(issue_rows[0])
    children = [link(issue, parent) for issue in issue_rows]
    for child in children:
        data = rt.verified_remote(child)
        assert data["Queue"]["Lifecycle"] == "investigations"
        assert child.incident_id == parent.pk
    assert rt.verified_remote(parent)["Queue"]["Lifecycle"] == "incidents"
    assert parent.investigations.count() == 3
    assert len({child.issue.organization_id for child in children}) == 2
    # Retain remote identities; simulate only a lost local acknowledgment and recover using GET.
    child = children[0]
    identity = child.remote_id
    RTTicket.objects.filter(pk=child.pk).update(
        remote_id=None, state="uncertain", last_attempt=timezone.now()
    )
    with patch("portal.rt.api", wraps=rt.api) as reads:
        rt.reconcile(child.pk, actor)
        assert all(call.args[1] == "GET" for call in reads.call_args_list)
    child.refresh_from_db()
    assert child.remote_id == identity
    for issue, old in zip(issue_rows, before):
        issue.refresh_from_db()
        assert (issue.status, issue.active) == old
    with httpx.Client(
        verify=os.environ["SSL_CERT_FILE"], trust_env=False, follow_redirects=False, timeout=10
    ) as client:
        for name in ["RT_BUNDLED_COMPANY_TOKEN", "RT_BUNDLED_CIRCL_TOKEN"]:
            for row in [parent, *children]:
                response = client.get(
                    instance.base_url + f"/REST/2.0/ticket/{row.remote_id}",
                    headers={"Authorization": "token " + os.environ[name]},
                )
                assert response.status_code in {403, 404}, "Ordinary RT bridge can read CIRCL RTIR evidence"
    print(
        "Verified native RTIR Incident and three linked asset Investigations across two companies, exact lifecycles, scoped key denial and GET-only lost-ack recovery; asset assessments unchanged."
    )
