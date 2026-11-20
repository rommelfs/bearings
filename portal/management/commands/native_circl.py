"""Explicit first native CIRCL source; no registration, consent, contacts or identity inference."""

import json
import sys
import uuid
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from portal.access import audit
from portal.models import Organization, InventorySource, NetBoxInstance, FlowIntelInstance


class Command(BaseCommand):
    help = "Plan/create the native CIRCL pilot binding. JSON metadata only on stdin; no API keys."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        actor = (
            get_user_model()
            .objects.filter(username=options["actor"], is_active=True, is_superuser=True)
            .first()
        )
        if not actor:
            raise CommandError("An active platform administrator is required")
        with transaction.atomic():
            organizations = list(
                Organization.objects.select_for_update().filter(
                    name__iexact="CIRCL", merged_into__isnull=True
                )
            )
            if len(organizations) > 1 or (organizations and organizations[0].merged_into_id):
                raise CommandError("Ambiguous or merged CIRCL organization; reconcile explicitly")
            org = organizations[0] if organizations else None
            source = (
                InventorySource.objects.select_for_update().filter(organization=org).first() if org else None
            )
            if not options["apply"]:
                self.stdout.write(
                    json.dumps(
                        {
                            "organization": org.pk if org else None,
                            "source": str(source.pk) if source else None,
                            "mode": source.mode if source else None,
                            "assets": source.asset_set.count() if source else 0,
                        }
                    )
                )
                return
            data = json.load(sys.stdin)
            key = uuid.UUID(data["key"]).hex
            netbox_name, flow_name = "native-circl-" + key, "native-circl-" + key
            nb = NetBoxInstance.objects.filter(name=netbox_name).first()
            flow = FlowIntelInstance.objects.filter(name=flow_name).first()
            if source and not (source.mode == "manual" and not source.asset_set.exists()):
                if not nb or source.instance_id != nb.pk or source.tenant_id != data["tenant"]:
                    raise CommandError(
                        "Existing authoritative inventory retained; reviewed migration required"
                    )
            if not org:
                if Organization.objects.filter(slug="circl").exists():
                    raise CommandError("CIRCL slug already assigned; no name-based adoption")
                org = Organization.objects.create(name="CIRCL", slug="circl", operator_visibility=True)
                audit(actor, org, "organization.native_created", org.pk)
            nb_values = dict(
                base_url="https://netbox.bearings.circl.lu",
                browser_url="https://netbox.bearings.circl.lu",
                token_env_var="NETBOX_NATIVE_CIRCL_TOKEN",
                organization=org,
                access_mode="read_only",
                auth_scheme="Bearer",
            )
            flow_values = dict(
                base_url="https://flowintel.bearings.circl.lu",
                browser_url="https://flowintel.bearings.circl.lu",
                bearings_url="https://bearings.circl.lu",
                token_env_var="FLOWINTEL_NATIVE_CIRCL_TOKEN",
                service_org_id=data["flow_org"],
            )
            for instance, model, name, values in [
                (nb, NetBoxInstance, netbox_name, nb_values),
                (flow, FlowIntelInstance, flow_name, flow_values),
            ]:
                if instance:
                    if (
                        any(getattr(instance, field) != value for field, value in values.items())
                        or not instance.enabled
                    ):
                        raise CommandError("Retained connector policy changed; no restoration")
                else:
                    instance = model(name=name, **values)
                    instance.full_clean()
                    instance.save()
                if model is NetBoxInstance:
                    nb = instance
            if not source:
                source = InventorySource(
                    organization=org, mode="central", instance=nb, tenant_id=data["tenant"]
                )
            elif source.mode == "manual":
                source.mode, source.instance, source.tenant_id = "central", nb, data["tenant"]
            source.full_clean()
            source.save()
            audit(actor, org, "inventory.native_bound", source.pk, tenant=data["tenant"])
            self.stdout.write(
                json.dumps(
                    {
                        "organization": org.pk,
                        "source": str(source.pk),
                        "tenant": source.tenant_id,
                        "read_only": True,
                    }
                )
            )
