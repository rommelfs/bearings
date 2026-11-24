"""Operator-only policy for any existing customer-owned or central authoritative binding."""

import json
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from portal.access import audit
from portal.connectors.http import ConnectorError, request_json
from portal.connectors.netbox import connection, in_scope
from portal.models import InventorySource, AgentDevice, Asset


class Command(BaseCommand):
    help = "Plan/enable/revoke inventory export on an existing source; never changes endpoint, tenant or credentials"

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--source", required=True)
        network = parser.add_mutually_exclusive_group(required=True)
        network.add_argument("--vrf", type=int)
        network.add_argument("--inventory-only", action="store_true")
        network.add_argument("--disable", action="store_true")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--bind-asset",
            help="Explicitly mark one already-linked NetBox host by its existing local UUID/external ID; never by hostname",
        )

    def handle(self, *args, **options):
        actor = (
            get_user_model()
            .objects.filter(username=options["actor"], is_active=True, is_superuser=True)
            .first()
        )
        if not actor:
            raise CommandError("An active platform administrator is required")
        if options["vrf"] is not None and options["vrf"] < 1:
            raise CommandError("VRF ID must be positive")
        with transaction.atomic():
            source = (
                InventorySource.objects.select_for_update(of=("self",))
                .select_related("instance", "organization")
                .get(pk=options["source"])
            )
            if source.organization.merged_into_id:
                raise CommandError("Select an active canonical company")
            rules = {} if options["disable"] else {"inventory": True, "vrf": options["vrf"]}
            result = {
                "source": str(source.pk),
                "organization": source.organization_id,
                "instance": str(source.instance_id),
                "tenant": source.tenant_id,
                "policy": rules,
                "applied": options["apply"],
                "current_policy": source.agent_export_policy,
            }
            binding = None
            if options["bind_asset"]:
                if not rules:
                    raise CommandError("Binding cannot accompany revocation")
                binding = (
                    Asset.objects.select_for_update()
                    .filter(
                        pk=options["bind_asset"],
                        source=source,
                        organization=source.organization,
                        state="synced",
                    )
                    .first()
                )
                if (
                    not binding
                    or not binding.external_id
                    or binding.object_type not in {"dcim.device", "virtualization.virtualmachine"}
                ):
                    raise CommandError("Select one confirmed host on this exact source")
                if not AgentDevice.objects.filter(
                    asset=binding,
                    source=source,
                    organization=source.organization,
                    enabled=True,
                    expires_at__gt=timezone.now(),
                ).exists():
                    raise CommandError("An active explicitly bound client is required")
                result["binding"] = {
                    "asset": str(binding.pk),
                    "external_id": binding.external_id,
                    "type": binding.object_type,
                }
            if options["apply"]:
                if rules:
                    try:
                        _, base, headers = connection(source, write=True)
                        if rules["vrf"] is not None:
                            row = request_json(
                                "GET", base + f"/api/ipam/vrfs/{rules['vrf']}/", headers=headers
                            )
                            if (
                                row.get("id") != rules["vrf"]
                                or row.get("enforce_unique") is not True
                                or not in_scope(source, row)
                            ):
                                raise ConnectorError("VRF scope or uniqueness is incompatible")
                    except ConnectorError:
                        raise CommandError(
                            "Writable approved connector and an explicitly scoped unique VRF are required"
                        ) from None
                    if binding:
                        path = (
                            (
                                "/api/virtualization/virtual-machines/"
                                if binding.object_type == "virtualization.virtualmachine"
                                else "/api/dcim/devices/"
                            )
                            + binding.external_id
                            + "/"
                        )
                        try:
                            row = request_json("GET", base + path, headers=headers)
                            fields = row.get("custom_fields", {})
                            if (
                                str(row.get("id")) != binding.external_id
                                or not in_scope(source, row)
                                or not isinstance(fields, dict)
                                or fields.get("bearings_id") not in (None, "", str(binding.pk))
                            ):
                                raise ConnectorError("Existing host identity or ownership conflicts")
                            if fields.get("bearings_id") != str(binding.pk):
                                row = request_json(
                                    "PATCH",
                                    base + path,
                                    headers=headers,
                                    json={"custom_fields": {"bearings_id": str(binding.pk)}},
                                )
                            if (
                                str(row.get("id")) != binding.external_id
                                or not in_scope(source, row)
                                or row.get("custom_fields", {}).get("bearings_id") != str(binding.pk)
                            ):
                                raise ConnectorError("Host marker acknowledgement differs")
                        except ConnectorError:
                            raise CommandError(
                                "Explicit host binding unconfirmed; preserve identity and review the exact NetBox object"
                            ) from None
                        audit(
                            actor,
                            source.organization,
                            "inventory.export_host_bound",
                            binding.pk,
                            external_id=binding.external_id,
                        )
                    source.agent_managed = True
                source.agent_export_policy = rules
                source.save(update_fields=["agent_managed", "agent_export_policy"])
                if rules:
                    # Report/export workers lock device before source. Queue only after
                    # releasing this source lock to avoid the inverse lock order.
                    source_id, organization_id = source.pk, source.organization_id
                    transaction.on_commit(
                        lambda: AgentDevice.objects.filter(
                            source_id=source_id,
                            organization_id=organization_id,
                            enabled=True,
                            expires_at__gt=timezone.now(),
                        ).update(netbox_export_pending=True, netbox_export_after=timezone.now())
                    )
                audit(
                    actor,
                    source.organization,
                    "inventory.export_policy",
                    source.pk,
                    enabled=bool(rules),
                    vrf=rules.get("vrf"),
                )
            self.stdout.write(json.dumps(result))
