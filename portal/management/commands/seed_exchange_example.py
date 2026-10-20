"""An explicit, repeatable exercise, never a real-company assessment or a scanner."""

import json
import os
import uuid
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from portal.access import can_edit
from portal.connectors.http import ConnectorError
from portal.connectors.vulnerability_lookup import lookup
from portal.intelligence import default_catalog, link_risk
from portal.models import (
    Asset,
    Finding,
    Installation,
    InventorySource,
    InventoryWrite,
    Membership,
    Organization,
    Product,
)
from portal.services import persist_lookup, process_write, transition_finding

CVE = "CVE-2026-70571"
BUILD = "15.2.1748.54"
PRODUCT = "Microsoft Exchange Server 2019 Cumulative Update 15"
RISK_UUIDS = ["7f9fc1a8-4f02-11e9-b3ea-0800277f0571"]
CONTEXT = (
    "SYNTHETIC EXERCISE — not a real company's inventory. Exchange 2019 CU15 build 15.2.1748.54 "
    "is assumed installed and unpatched; Microsoft lists CU15 builds below 15.02.1748.055 as affected "
    "by CVE-2026-70571. The example analyst manually compared the edition and build. "
    "Network reachability is an exercise assumption, not a scan result. "
    "Possible consequences if exploitation succeeds: reading confidential email, modifying messages or "
    "server data, mail-service outage and follow-on compromise using the server's access. "
    "Lateral movement depends on privileges and segmentation; it is not established by this CVE. "
    "No exploitation or compromise is observed. Next: verify edition/build and reachability, "
    "apply the vendor update for the exact edition, verify remediation, and investigate compromise "
    "separately if indicators warrant it. CVSS is source severity, not organizational risk."
)
MAPPING_REASON = (
    "SYNTHETIC EXERCISE: successful remote code execution on this mail server could permit malware "
    "installation and compromise email confidentiality, integrity and availability. The server/malware/"
    "patch-management scenario is an analyst-selected hypothesis: the deliberately unpatched example "
    "supports reviewing patch management, but does not prove an organizational process failure. "
    "Mail theft, tampering, outage and any follow-on access are possible consequences, not observations. "
    "Likelihood, business impact, treatment owner and risk acceptance remain unassessed."
)


class Command(BaseCommand):
    help = "Add a SYNTHETIC unpatched Exchange example using live public CVE/MOSP evidence; no scans or notifications"

    def add_arguments(self, parser):
        parser.add_argument(
            "--bundled", action="store_true", help="Use only the guarded bundled writable NetBox lab"
        )
        parser.add_argument("--actor", default="company-admin", help="Existing active example editor account")

    def source(self, user, bundled):
        if bundled:
            from docker.dev.smoke import lab_sources

            try:
                config = json.loads(Path("/run/bearings/secrets/connections.json").read_text())
                if os.getenv("BEARINGS_DEV_STACK") != "1" or config.get("mode") != "bundled":
                    raise CommandError("Exchange example refuses external NetBox configurations")
                if any(
                    c["base_url"] != "https://netbox.bearings.test"
                    or not c["name"].startswith("bundled-netbox-")
                    for c in config["connections"]
                ):
                    raise CommandError("Unexpected lab identity; refusing inventory writes")
                source = lab_sources(config)["read_write"]
            except (OSError, ValueError, KeyError, RuntimeError):
                raise CommandError(
                    "Expected bundled lab identity/capability unavailable; no external writes attempted"
                ) from None
        else:
            with transaction.atomic():
                org, created = Organization.objects.get_or_create(
                    slug="exchange-example",
                    defaults={"name": "Exchange Company (SYNTHETIC)", "operator_visibility": True},
                )
                source, _ = InventorySource.objects.get_or_create(
                    organization=org, defaults={"mode": "development"}
                )
                if source.mode != "development" or source.instance_id:
                    raise CommandError("Native Exchange example refuses NetBox-backed workspaces")
                if created:
                    Membership.objects.create(user=user, organization=org, role="admin")
                if not can_edit(user, org):
                    raise CommandError(
                        "Example actor cannot edit this workspace; existing permissions preserved"
                    )
        if not can_edit(user, source.organization):
            raise CommandError("Example actor cannot edit the bundled workspace")
        return source

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Exchange example is restricted to explicit local development")
        user = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
        if not user:
            raise CommandError("Existing active actor required; initialize the development accounts first")
        source = self.source(user, options["bundled"])
        try:
            origin, payload = lookup(CVE)
        except ConnectorError:
            raise CommandError(
                "Live CVE retrieval failed; no synthetic vulnerability record substituted"
            ) from None
        containers = payload.get("containers")
        cna = containers.get("cna") if isinstance(containers, dict) else None
        affected = cna.get("affected") if isinstance(cna, dict) else None
        expected_range = False
        for item in affected if isinstance(affected, list) else []:
            if not isinstance(item, dict) or item.get("product") != PRODUCT:
                continue
            versions = item.get("versions")
            expected_range |= isinstance(versions, list) and any(
                isinstance(v, dict)
                and v.get("status") == "affected"
                and v.get("version") == "15.02.0.0"
                and v.get("lessThan") == "15.02.1748.055"
                and v.get("versionType") == "custom"
                for v in versions
            )
        if payload.get("cveMetadata", {}).get("state") != "PUBLISHED" or not expected_range:
            raise CommandError(
                "Live CVE no longer identifies the expected Exchange edition/range; review the exercise"
            )
        with transaction.atomic():
            InventorySource.objects.select_for_update().get(pk=source.pk)
            asset, _ = Asset.objects.get_or_create(
                pk=uuid.uuid5(uuid.NAMESPACE_URL, "bearings:exchange-example:" + str(source.pk)),
                defaults={
                    "organization": source.organization,
                    "source": source,
                    "name": "exchange-example-01 (SYNTHETIC)",
                    "kind": "server",
                    "criticality": "high",
                    "responsible_team": "Synthetic messaging team",
                },
            )
            if asset.source_id != source.pk or asset.organization_id != source.organization_id:
                raise CommandError("Existing example identity conflicts; preserved unchanged")
            job, _ = InventoryWrite.objects.get_or_create(asset=asset)
            product, _ = Product.objects.get_or_create(
                organization=source.organization,
                name=PRODUCT,
                identifier="cpe:2.3:a:microsoft:exchange_server_2019:*:cumulative_update_15:*:*:*:*:*:*",
            )
            installation, _ = Installation.objects.get_or_create(
                asset=asset,
                product=product,
                defaults={"version": BUILD, "build": BUILD, "edition": "2019 CU15"},
            )
            if installation.version != BUILD or installation.build != BUILD or asset.lifecycle != "active":
                raise CommandError("Example was changed or retired; local remediation is preserved")
        if not job.completed_at:
            process_write(job.pk)
        asset.refresh_from_db()
        if asset.state != "synced":
            raise CommandError(
                "Example inventory write remains unconfirmed; inspect source health and retry later"
            )
        existed = Finding.objects.filter(
            installation=installation,
            record__source=origin,
            record__external_id=CVE,
            rule="manual-cve-review/v1",
        ).exists()
        finding = persist_lookup(user, installation, origin, CVE, payload)
        if not existed:
            finding.explanation = CONTEXT
            finding.save(update_fields=["explanation"])
            transition_finding(user, finding, "under_review", CONTEXT, "affected")
        self.stdout.write(
            f"SYNTHETIC Exchange example ready: organization {source.organization.slug}, finding {finding.pk}. Manual example assessment; no scans, compromise assertion or notifications."
        )
        if options["bundled"]:
            self.stdout.write(
                "IP/DNS/datacenter/rack placement is a separate bundled-lab step. "
                "For this existing case run: python3 scripts/dev.py example-exchange --inventory-only. "
                "The full scripts/dev.py example-exchange helper includes placement and import automatically."
            )
        try:
            catalog = default_catalog()
            for risk_uuid in RISK_UUIDS:
                # Preserve withdrawn links and explicit user decisions on repeated demo setup.
                if not finding.risk_links.filter(
                    risk_revision__risk__source=catalog, risk_revision__risk__uuid=risk_uuid
                ).exists():
                    link_risk(user, finding, catalog.pk, risk_uuid, MAPPING_REASON)
        except ConnectorError:
            raise CommandError(
                "Exchange finding retained; live MOSP mapping failed. Retry without losing analyst decisions"
            ) from None
        self.stdout.write(
            "Live CVE and CC0 MOSP scenario linked; business risk remains unassessed. Review the in-app analyst queue."
        )
