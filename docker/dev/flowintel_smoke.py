"""Optional real lab proof. Synthetic cases only; no notification/scan/remediation execution."""

import json
import os
import time
from pathlib import Path
from unittest.mock import patch
import httpx
from django.contrib.auth import get_user_model
from django.utils import timezone
from portal import flowintel
from portal.models import Asset, FlowIntelCase, FlowIntelInstance, Installation
from portal.services import persist_lookup
from .smoke import lab_sources


def main():
    if os.getenv("BEARINGS_FLOWINTEL") != "1":
        return
    config = json.loads(Path("/run/bearings/secrets/connections.json").read_text())
    if config.get("mode") != "bundled":
        raise RuntimeError("FlowIntel smoke requires bundled mode")
    sources = lab_sources(config)
    instance = FlowIntelInstance.objects.get(name="bundled-flowintel")
    if (
        instance.base_url != "https://flowintel.bearings.test"
        or instance.token_env_var != "FLOWINTEL_BUNDLED_TOKEN"
        or not instance.enabled
    ):
        raise RuntimeError("FlowIntel lab identity/policy changed; refusing smoke writes")
    actor = get_user_model().objects.get(username="circl-analyst", is_active=True)
    outsider = os.environ["FLOWINTEL_LAB_OUTSIDER_TOKEN"]
    for item in config["connections"]:
        source = sources[item["access_mode"]]
        asset = Asset.objects.get(pk=item["assets"][0]["id"], source=source)
        installation = Installation.objects.get(
            asset=asset, product__identifier="pkg:maven/org.apache.logging.log4j/log4j-core"
        )
        finding = persist_lookup(
            None,
            installation,
            "fixture://flowintel-smoke/SYNTHETIC",
            "CVE-2021-44228",
            {
                "fixture": True,
                "note": "Synthetic workflow proof, not fetched evidence",
                "containers": {
                    "cna": {
                        "title": "SYNTHETIC Log4j review for FlowIntel pilot",
                        "metrics": [{"cvssV3_1": {"version": "3.1", "baseScore": 10.0}}],
                    }
                },
            },
        )
        initial = (finding.status, finding.analyst_applicability)
        binding = flowintel.preview(
            actor, finding, instance, None, "SYNTHETIC bundled FlowIntel workflow and isolation proof"
        )
        if binding.state == "draft":
            flowintel.approve(actor, binding.pk)
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            flowintel.process(binding.pk)
            binding.refresh_from_db()
            if binding.state == "linked":
                break
            if binding.state in {"uncertain", "blocked"}:
                raise RuntimeError("Live FlowIntel hand-off requires investigation; no automatic retry")
            time.sleep(1)
        assert binding.state == "linked", "FlowIntel task playbook did not complete"
        flowintel.refresh(binding.pk)
        binding.refresh_from_db()
        assert len(binding.summary["tasks"]) == 4 and binding.remote_uuid
        assert len(binding.summary["tasks"]) == binding.tasks.count()
        assert (
            flowintel.preview(actor, finding, instance, None, "Ignored replacement preview").pk == binding.pk
        )
        # Simulate a lost case acknowledgment only for this explicitly synthetic fixture.
        # Recover the durable mapping through the real read API, never by issuing another POST.
        expected = (binding.remote_id, binding.remote_uuid)
        task_ids = list(binding.tasks.order_by("step").values_list("remote_id", flat=True))
        FlowIntelCase.objects.filter(pk=binding.pk, state="linked").update(
            remote_id=None, remote_uuid=None, state="uncertain", last_attempt=timezone.now()
        )
        original_api = flowintel.api
        with patch("portal.flowintel.api", wraps=original_api) as reads:
            flowintel.reconcile(binding.pk, actor)
            assert reads.call_count > 0
            assert all(call.args[1] == "GET" for call in reads.call_args_list)
        binding.refresh_from_db()
        assert (binding.remote_id, binding.remote_uuid) == expected
        assert list(binding.tasks.order_by("step").values_list("remote_id", flat=True)) == task_ids
        with httpx.Client(
            verify=os.environ["SSL_CERT_FILE"], trust_env=False, follow_redirects=False, timeout=8
        ) as client:
            response = client.get(
                instance.base_url + f"/api/case/{binding.remote_id}", headers={"X-API-KEY": outsider}
            )
            assert response.status_code in {403, 404}, (
                "An unrelated FlowIntel organization could read a private case"
            )
            assert binding.title not in response.text
        finding.refresh_from_db()
        assert (finding.status, finding.analyst_applicability) == initial
    print(
        "Verified FlowIntel private cases for both NetBox RO/RW organizations, four tasks per case, current TLS, outsider denial, repeat identity, real lost-ack read-only reconciliation and GET-only status feedback. No notifications or remediation executed."
    )
