"""Explicit repeatable synthetic lifecycle/exposure exercise; no real claims or external writes."""

import ipaddress
import uuid
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from portal import issues, plum
from portal.asset_context import asset_context
from portal.models import AssetIssue, Asset, InfrastructureClaim, PlumInstance, PlumSnapshot
from .seed_exchange_example import Command as ExchangeCommand

NAMESPACE = uuid.UUID("051ae033-2cc0-4c0e-b1b3-6216cb948906")


class Command(BaseCommand):
    help = "Add guarded SYNTHETIC lifecycle/Plum examples to existing demo inventory; no scans or messages"

    def add_arguments(self, parser):
        parser.add_argument("--bundled", action="store_true")
        parser.add_argument("--actor", default="company-admin")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Synthetic issues require DEBUG")
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
        if not actor:
            raise CommandError("Existing active demo editor required")
        source = ExchangeCommand().source(actor, options["bundled"])
        asset = Asset.objects.filter(source=source, name="exchange-example-01 (SYNTHETIC)").first()
        if not asset:
            asset = (
                Asset.objects.filter(
                    source=source,
                    lifecycle="active",
                    object_type__in=["dcim.device", "virtualization.virtualmachine", ""],
                )
                .order_by("pk")
                .first()
            )
        if not asset:
            raise CommandError("Seed/import the synthetic inventory first")
        for kind, days, priority, consequence in [
            ("support", -7, "high", "Security fixes and incident support might no longer be covered."),
            ("license", 12, "review", "Mail processing may be interrupted when the entitlement expires."),
            (
                "warranty",
                28,
                "low",
                "Hardware failure could require unbudgeted replacement and longer recovery.",
            ),
            ("eol", 45, "high", "An unsupported component may require migration or replacement."),
        ]:
            identity = uuid.uuid5(NAMESPACE, f"{asset.pk}/{kind}")
            if AssetIssue.objects.filter(pk=identity).exists():
                continue
            issues.save_issue(
                actor,
                AssetIssue(pk=identity, organization=source.organization),
                {
                    "asset": asset,
                    "kind": kind,
                    "title": f"SYNTHETIC · {kind.title()} lifecycle review",
                    "priority": priority,
                    "event_date": timezone.localdate() + timedelta(days=days),
                    "owner_team": "Synthetic infrastructure team",
                    "fact_scope": "entitlement" if kind != "eol" else "asset",
                    "contract_reference": f"SYNTHETIC-{kind.upper()}-1",
                    "source_label": "SYNTHETIC exercise contract · no vendor assertion",
                    "evidence_text": "Invented exercise date and contract. Verify actual entitlement/vendor evidence before any operational decision.",
                    "fact_status": "unverified",
                    "consequence": consequence,
                    "shareable": True,
                    "next_action": "Verify the real contract, assign an owner and agree a treatment deadline.",
                },
                "Explicit synthetic exercise; no production assessment",
            )
        facts = asset_context(asset)
        addresses = [row["address"] for row in facts["addresses"] if "/" not in row["address"]]
        address = next(
            (
                value
                for value in addresses
                if ipaddress.ip_address(value) in ipaddress.ip_network("192.0.2.0/24")
            ),
            None,
        )
        if address:
            fixture, created = PlumInstance.objects.get_or_create(
                name="SYNTHETIC Plum historical exercise",
                defaults={"base_url": "https://plum.example.invalid", "fixture": True, "enabled": True},
            )
            if created:
                fixture.organizations.add(source.organization)
            if not fixture.fixture or not fixture.enabled:
                raise CommandError("Synthetic source policy changed; existing configuration preserved")
            existing = (
                PlumSnapshot.objects.filter(source=fixture, organization=source.organization, ip=address)
                .order_by("window_start")
                .first()
            )
            if not existing:
                begin = timezone.now().replace(microsecond=0) - timedelta(days=20)
                stop = begin + timedelta(days=7)
                InfrastructureClaim.objects.get_or_create(
                    organization=source.organization,
                    kind="ip",
                    value=address,
                    defaults={
                        "status": "verified",
                        "valid_from": begin - timedelta(days=1),
                        "method": "SYNTHETIC bundled exercise only",
                        "reviewed_at": timezone.now(),
                    },
                )
                for start, end, ports in [
                    (begin, stop, [(443, "tcp"), (53, "udp")]),
                    (stop, stop + timedelta(days=7), [(443, "tcp"), (3389, "tcp")]),
                ]:
                    plum.ingest(
                        actor,
                        source.organization,
                        fixture,
                        {
                            "result": {
                                "ip": address,
                                "start": start.isoformat(),
                                "stop": end.isoformat(),
                                "report_count": 2,
                                "ports": [
                                    {
                                        "port": port,
                                        "protocol": protocol,
                                        "tags": ["SYNTHETIC:exercise"],
                                        "first_seen": start.isoformat(),
                                        "last_seen": end.isoformat(),
                                    }
                                    for port, protocol in ports
                                ],
                            }
                        },
                    )
        self.stdout.write(
            "SYNTHETIC lifecycle issues ready; existing decisions preserved. Exposure windows added only for a mapped documentation IP. No scans, external writes, cases or notifications."
        )
