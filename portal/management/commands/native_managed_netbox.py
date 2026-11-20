"""Explicit migration of the retained native CIRCL binding; never adopt a host by name upstream."""

import json
import sys
import uuid
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from portal.access import audit
from portal.connectors.http import ConnectorError
from portal.connectors.netbox import query_objects
from portal.inventory import refresh_inventory
from portal.models import (
    Asset,
    AgentDevice,
    Finding,
    Installation,
    InventorySource,
    InventoryWrite,
    NetBoxInstance,
    VIRTUALIZATION_TYPES,
)
from portal.services import process_write


NATIVE_BASE = "https://netbox.bearings.circl.lu"


class Command(BaseCommand):
    help = (
        "Plan, apply or verify retained native CIRCL managed inventory. Non-secret binding metadata on stdin."
    )

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--host", required=True)
        parser.add_argument("--kind", choices=["vm", "server", "desktop", "laptop"], default="vm")
        parser.add_argument("--virtualization", choices=[v for v, _ in VIRTUALIZATION_TYPES], default="")
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--apply", action="store_true")
        mode.add_argument("--verify", action="store_true")

    def handle(self, *args, **options):
        actor = (
            get_user_model()
            .objects.filter(username=options["actor"], is_active=True, is_superuser=True)
            .first()
        )
        if not actor:
            raise CommandError("An active platform administrator is required")
        data = json.load(sys.stdin)
        key = uuid.UUID(data["key"]).hex
        if options["virtualization"] and options["kind"] != "vm":
            raise CommandError("Virtualization tags require a VM")
        with transaction.atomic():
            instance = NetBoxInstance.objects.filter(
                name="native-circl-" + key,
                base_url=NATIVE_BASE,
                token_env_var="NETBOX_NATIVE_CIRCL_TOKEN",
                auth_scheme="Bearer",
                enabled=True,
                organization__merged_into__isnull=True,
            ).first()
            if not instance:
                raise CommandError(
                    "Retained native NetBox identity is unavailable; no endpoint or credentials changed"
                )
            source = (
                InventorySource.objects.select_for_update()
                .filter(
                    instance=instance,
                    organization_id=instance.organization_id,
                    mode="central",
                    tenant_id=data["tenant"],
                )
                .first()
            )
            if not source:
                raise CommandError("Retained native company/source/tenant binding differs")
            instance = NetBoxInstance.objects.select_for_update(of=("self",)).get(pk=instance.pk)
            if (
                not instance.enabled
                or instance.organization_id != source.organization_id
                or instance.base_url != NATIVE_BASE
                or instance.auth_scheme != "Bearer"
                or instance.token_env_var != "NETBOX_NATIVE_CIRCL_TOKEN"
            ):
                raise CommandError("Native instance policy changed")
            candidates = list(
                Asset.objects.select_for_update().filter(
                    source=source,
                    organization_id=source.organization_id,
                    name__iexact=options["host"],
                    lifecycle="active",
                )
            )
            if len(candidates) != 1:
                raise CommandError(
                    "Select exactly one existing active Bearings host; no fuzzy matching or upstream hostname adoption"
                )
            asset = candidates[0]
            if asset.external_id and ((asset.kind == "vm") != (options["kind"] == "vm")):
                raise CommandError(
                    "Existing external identity cannot be changed between physical and virtual inventory"
                )
            devices = AgentDevice.objects.filter(
                asset=asset,
                source=source,
                organization_id=source.organization_id,
                enabled=True,
                expires_at__gt=timezone.now(),
            )
            if not devices.exists():
                raise CommandError("An active enrolled device on this exact source is required")
            before_devices = set(devices.values_list("pk", "public_key"))
            before_software = set(Installation.objects.filter(asset=asset).values_list("pk", flat=True))
            before_findings = set(
                Finding.objects.filter(installation__asset=asset).values_list("pk", flat=True)
            )
            plan = {
                "organization": source.organization_id,
                "source": str(source.pk),
                "asset": str(asset.pk),
                "tenant": source.tenant_id,
                "kind": options["kind"],
                "virtualization": options["virtualization"],
                "managed": source.agent_managed,
                "existing_external_id": asset.external_id,
            }
            if not options["apply"] and not options["verify"]:
                self.stdout.write(json.dumps(plan))
                return
            if options["verify"] and (
                asset.kind != options["kind"] or asset.virtualization_type != options["virtualization"]
            ):
                raise CommandError("Requested inventory kind/virtualization differs from the retained host")
            if options["verify"] and not source.agent_managed:
                raise CommandError("Managed inventory has not been enabled")
            if options["apply"]:
                defaults = data["defaults"]
                for field in ["site", "role", "device_type"]:
                    value = defaults[field]
                    if type(value) is not int or value < 1:
                        raise CommandError("Native reference IDs must be positive integers")
                    name = field + "_id"
                    current = getattr(instance, name)
                    if current is not None and current != value:
                        raise CommandError(
                            "Existing native placement defaults changed; no silent replacement"
                        )
                    setattr(instance, name, value)
                tags = defaults["virtualization_tags"]
                if not isinstance(tags, dict) or any(
                    k not in dict(VIRTUALIZATION_TYPES) or not k or type(v) is not int or v < 1
                    for k, v in tags.items()
                ):
                    raise CommandError("Invalid native virtualization taxonomy")
                if instance.virtualization_tags and instance.virtualization_tags != tags:
                    raise CommandError("Existing native virtualization taxonomy changed")
                if options["virtualization"] and options["virtualization"] not in tags:
                    raise CommandError("Requested virtualization tag was not provisioned")
                instance.virtualization_tags = tags
                instance.access_mode = "read_write"
                instance.full_clean()
                instance.save()
                source.agent_managed = True
                source.full_clean()
                source.save(update_fields=["agent_managed"])
                if asset.kind != options["kind"] or asset.virtualization_type != options["virtualization"]:
                    asset.kind = options["kind"]
                    asset.virtualization_type = options["virtualization"]
                    asset.full_clean()
                    asset.save(update_fields=["kind", "virtualization_type"])
                job, created = InventoryWrite.objects.get_or_create(
                    asset=asset, defaults={"agent_managed": True}
                )
                if not created:
                    job.agent_managed = True
                    job.completed_at = None
                    job.next_attempt = timezone.now()
                    job.save(update_fields=["agent_managed", "completed_at", "next_attempt"])
                audit(
                    actor,
                    asset.organization,
                    "inventory.managed_enabled",
                    asset.pk,
                    tenant=source.tenant_id,
                    virtualization=asset.virtualization_type,
                )
        try:
            job = InventoryWrite.objects.filter(asset=asset, completed_at__isnull=True).first()
            if options["apply"] and job:
                process_write(job.pk, force=True)
            asset.refresh_from_db()
            source.refresh_from_db()
            if not asset.external_id or asset.state != "synced":
                raise ConnectorError("NetBox registration remains unconfirmed")
            kind = "virtual-machines" if asset.kind == "vm" else "devices"
            rows = query_objects(source, kind)
            matches = [
                r for r in rows if r["record"].get("custom_fields", {}).get("bearings_id") == str(asset.pk)
            ]
            if len(matches) != 1 or matches[0]["external_id"] != asset.external_id:
                raise ConnectorError("NetBox UUID/external identity verification failed")
            tags = matches[0]["record"].get("tags", [])
            if asset.virtualization_type and not any(
                t.get("id") == source.instance.virtualization_tags.get(asset.virtualization_type)
                for t in tags
                if isinstance(t, dict)
            ):
                raise ConnectorError("NetBox virtualization tag verification failed")
            refresh_inventory(source.pk)
            asset.refresh_from_db()
            if (
                asset.inventory_seen_at is None
                or asset.missing_since
                or asset.object_type != matches[0]["object_type"]
            ):
                raise ConnectorError("Bearings import verification failed")
            if (
                not before_devices
                <= set(AgentDevice.objects.filter(asset=asset).values_list("pk", "public_key"))
                or not before_software
                <= set(Installation.objects.filter(asset=asset).values_list("pk", flat=True))
                or not before_findings
                <= set(Finding.objects.filter(installation__asset=asset).values_list("pk", flat=True))
            ):
                raise ConnectorError("Retained agent/software/review identity verification failed")
        except (ConnectorError, ValueError) as exc:
            raise CommandError(
                "Managed NetBox registration/verification is unconfirmed. Retry the same operation to reconcile by UUID; inspect source health without changing identity."
            ) from exc
        audit(
            actor, asset.organization, "inventory.managed_verified", asset.pk, external_id=asset.external_id
        )
        self.stdout.write(
            json.dumps(
                {
                    **plan,
                    "managed": source.agent_managed,
                    "external_id": asset.external_id,
                    "netbox_object": asset.object_type,
                    "uuid_match": True,
                    "tenant_match": True,
                    "import_match": True,
                    "agent_software_reviews_preserved": True,
                }
            )
        )
