"""Opt-in synthetic PHP installation with two genuine public CVE records."""

import json
import os
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from portal.connectors.http import ConnectorError
from portal.connectors.vulnerability_lookup import lookup
from portal.demo_data import KEY, capture
from portal.models import Asset, DemoDataset, DemoObject, Product, Installation, SourceRecord, Finding
from portal.services import persist_lookup

CVES = ("CVE-2026-109618", "CVE-2026-109619")
CONTEXT = (
    "SYNTHETIC guided exercise: PHP 8.4.26 is assumed installed, not discovered or scanned. "
    "The PHP CNA records list affected 8.4 versions below 8.4.27. Verify the exact vendor package, "
    "backports and runtime/request prerequisites before confirming applicability. "
    "CVE-2026-109618 concerns out-of-memory cleanup corruption; CVE-2026-109619 concerns stale global "
    "state between requests. Both describe possible RCE, not observed compromise. Successful exploitation "
    "could expose application data, permit tampering or interrupt service, depending on privileges and "
    "deployment. Inventory placement belongs to the host fixture; installation and exposure assumptions "
    "are synthetic. Next: inspect the PHP advisories, establish affectedness, identify an owner, plan "
    "a supported vendor fix, verify the deployed version and follow up. No automatic remediation, "
    "risk score or stakeholder notification is performed."
)


class Command(BaseCommand):
    help = "Seed a tracked synthetic PHP 8.4.26 case with live CVE-2026-109618 and CVE-2026-109619"

    def add_arguments(self, parser):
        parser.add_argument("--actor", default="platform-admin")
        parser.add_argument(
            "--bundled",
            action="store_true",
            help="Use an existing guarded bundled NetBox RW fixture; no NetBox writes",
        )

    def handle(self, *args, **options):
        actor = (
            get_user_model()
            .objects.filter(username=options["actor"], is_active=True, is_superuser=True)
            .first()
        )
        if not settings.DEBUG or not actor:
            raise CommandError("Requires DEBUG and an existing active platform superuser")
        if not DemoDataset.objects.filter(key=KEY, state="active").exists():
            raise CommandError("An active tracked showcase is required; removed data is not restored")
        payloads = []
        for identifier in CVES:
            try:
                source, payload = lookup(identifier)
            except ConnectorError:
                raise CommandError(
                    "Live PHP CVE retrieval failed; no substitute evidence or partial example was created"
                ) from None
            affected = payload.get("containers", {}).get("cna", {}).get("affected", [])
            expected = any(
                isinstance(row, dict)
                and row.get("vendor") == "PHP Group"
                and row.get("product") == "PHP"
                and any(
                    isinstance(v, dict)
                    and v.get("status") == "affected"
                    and v.get("version") == "8.4.*"
                    and v.get("lessThan") == "8.4.27"
                    and v.get("versionType") == "semver"
                    for v in row.get("versions", [])
                )
                for row in affected
            )
            if payload.get("cveMetadata", {}).get("state") != "PUBLISHED" or not expected:
                raise CommandError(
                    "Public PHP version conditions changed; review this exercise before seeding"
                )
            payloads.append((source, identifier, payload))
        with transaction.atomic():
            dataset = DemoDataset.objects.select_for_update().get(key=KEY)
            if dataset.state != "active":
                raise CommandError("Showcase removed while retrieving evidence; no example created")
            if options["bundled"]:
                from docker.dev.smoke import lab_sources

                try:
                    config = json.loads(Path("/run/bearings/secrets/connections.json").read_text())
                    if os.getenv("BEARINGS_DEV_STACK") != "1" or config.get("mode") != "bundled":
                        raise ValueError
                    source = lab_sources(config)["read_write"]
                    asset = (
                        Asset.objects.filter(source=source, object_type="dcim.device", lifecycle="active")
                        .order_by("name")
                        .first()
                    )
                except (OSError, ValueError, KeyError, RuntimeError):
                    raise CommandError(
                        "Requires the guarded bundled NetBox lab; external instances are refused"
                    ) from None
            else:
                ids = list(
                    dataset.entries.filter(model_label="portal.asset").values_list("object_pk", flat=True)
                )
                asset = (
                    Asset.objects.filter(
                        pk__in=ids,
                        organization__operator_visibility=True,
                        lifecycle="active",
                        source__mode="development",
                        source__instance__isnull=True,
                    )
                    .order_by("name")
                    .first()
                )
            if asset is None:
                raise CommandError(
                    "No suitable existing synthetic asset found; initialize/import the lab first"
                )

            def owned(row):
                if not DemoObject.objects.filter(
                    dataset=dataset, model_label=row._meta.label_lower, object_pk=str(row.pk)
                ).exists():
                    raise CommandError(
                        "An untracked conflicting record was preserved; example creation rolled back"
                    )

            with capture(dataset):
                product, _ = Product.objects.get_or_create(
                    organization=asset.organization, name="PHP (SYNTHETIC guided example)"
                )
                owned(product)
                installation, _ = Installation.objects.get_or_create(
                    asset=asset, product=product, defaults={"version": "8.4.26"}
                )
                owned(installation)
                for source, identifier, payload in payloads:
                    old = SourceRecord.objects.filter(
                        organization=asset.organization, source=source, external_id=identifier
                    ).first()
                    if old:
                        owned(old)
                    existing = Finding.objects.filter(
                        installation=installation, record__source=source, record__external_id=identifier
                    ).exists()
                    finding = persist_lookup(actor, installation, source, identifier, payload)
                    owned(finding)
                    if not existing:
                        finding.explanation = CONTEXT
                        finding.save(update_fields=["explanation"])
                    self.stdout.write(
                        f"Guided PHP case: /organizations/{asset.organization.slug}/findings/{finding.pk}/guide/"
                    )
        self.stdout.write(
            "Tracked PHP example ready. Existing versions, assessments, contact policies and source restrictions preserved. No NetBox writes, scans, cases or notifications."
        )
