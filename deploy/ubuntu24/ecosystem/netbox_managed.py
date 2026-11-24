"""Explicit native managed-inventory capability; capture JSON privately, never log tokens."""

import json
import sys
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from dcim.models import Device, DeviceType, DeviceRole, Manufacturer, Site, Interface
from ipam.models import IPAddress, VRF
from extras.models import CustomField, Tag
from users.models import ObjectPermission, Token
from virtualization.models import VirtualMachine, VMInterface
from netbox_inventory import provision

TECHNOLOGIES = ("lxc", "incus", "proxmox", "vmware", "kvm", "hyperv")


def permissions(user_id):
    return [
        {
            "id": p.pk,
            "actions": p.actions,
            "constraints": p.constraints,
            "enabled": p.enabled,
            "types": sorted(p.object_types.values_list("pk", flat=True)),
        }
        for p in ObjectPermission.objects.filter(users__id=user_id).order_by("pk")
    ]


@transaction.atomic
def manage(data):
    if data.get("verify_only") and not (data.get("saved") or {}).get("managed"):
        raise ValueError("Managed native policy has not been applied; verification never provisions")
    receipt = provision(data)
    marker = "Bearings managed inventory " + data["key"].replace("-", "")
    slug = "bearings-managed-" + data["key"].replace("-", "")
    if receipt.get("managed"):
        for model, field in [(Site, "site"), (DeviceRole, "role"), (DeviceType, "device_type")]:
            obj = model.objects.get(pk=receipt["defaults"][field])
            if obj.slug != slug or obj.description != marker:
                raise ValueError("Retained managed reference data changed; no restoration")
        dtype = DeviceType.objects.select_related("manufacturer").get(pk=receipt["defaults"]["device_type"])
        if dtype.manufacturer.slug != slug or dtype.manufacturer.description != marker:
            raise ValueError("Retained managed manufacturer changed")
        custom = CustomField.objects.get(name="bearings_id")
        if custom.type != "text" or not {
            ContentType.objects.get_for_model(Device).pk,
            ContentType.objects.get_for_model(VirtualMachine).pk,
        }.issubset(set(custom.object_types.values_list("pk", flat=True))):
            raise ValueError("Retained managed UUID custom field changed")
        for name, pk in receipt["defaults"]["virtualization_tags"].items():
            tag = Tag.objects.get(pk=pk)
            if tag.slug != name or tag.name.casefold() != name:
                raise ValueError("Retained virtualization tag changed")
        return inventory_export(receipt, data)

    if data.get("verify_only"):
        raise ValueError("Managed native policy has not been applied; no writes during verification")

    def owned(model, values):
        if model.objects.filter(slug=slug).exists():
            raise ValueError("Unrecorded managed reference data exists; reconcile explicitly")
        return model.objects.create(slug=slug, description=marker, **values)

    site = owned(Site, {"name": "Unspecified location (Bearings agent inventory) " + slug[-8:]})
    role = owned(DeviceRole, {"name": "Agent-reported host " + slug[-8:], "color": "315e73"})
    manufacturer = owned(
        Manufacturer, {"name": "Unspecified manufacturer (Bearings agent inventory) " + slug[-8:]}
    )
    dtype = owned(
        DeviceType,
        {"manufacturer": manufacturer, "model": "Unspecified agent-reported hardware", "u_height": 0},
    )
    custom, _ = CustomField.objects.get_or_create(
        name="bearings_id", defaults={"type": "text", "label": "Bearings asset UUID"}
    )
    if custom.type != "text":
        raise ValueError("Existing bearings_id custom field has incompatible type")
    custom.object_types.add(
        ContentType.objects.get_for_model(Device), ContentType.objects.get_for_model(VirtualMachine)
    )
    tags = {}
    for name in TECHNOLOGIES:
        tag, _ = Tag.objects.get_or_create(
            slug=name,
            defaults={
                "name": name,
                "description": "Virtualization technology; explicitly declared, not hardware attestation",
            },
        )
        if tag.name.casefold() != name:
            raise ValueError("Existing virtualization tag conflicts with expected taxonomy")
        tags[name] = tag.pk
    for p in ObjectPermission.objects.filter(users__id=receipt["user"]):
        if set(p.object_types.values_list("pk", flat=True)) & {
            ContentType.objects.get_for_model(Device).pk,
            ContentType.objects.get_for_model(VirtualMachine).pk,
        }:
            p.actions = ["view", "add", "change"]
            p.save(update_fields=["actions"])
    for model, constraint in [
        (Site, {"id": site.pk}),
        (DeviceRole, {"id": role.pk}),
        (DeviceType, {"id": dtype.pk}),
        (Manufacturer, {"id": manufacturer.pk}),
        (Tag, {"id__in": list(tags.values())}),
    ]:
        p = ObjectPermission.objects.create(
            name=slug + " " + model.__name__, actions=["view"], constraints=constraint
        )
        p.object_types.add(ContentType.objects.get_for_model(model))
        p.users.add(receipt["user"])
    token = Token.objects.select_for_update().get(pk=receipt["token_id"])
    token.write_enabled = True
    token.save(update_fields=["write_enabled"])
    return inventory_export(
        {
            **receipt,
            "managed": True,
            "permissions": permissions(receipt["user"]),
            "defaults": {
                "site": site.pk,
                "role": role.pk,
                "device_type": dtype.pk,
                "virtualization_tags": tags,
            },
        },
        data,
    )


def inventory_export(receipt, data):
    """Opt-in native policy extension; never widen a customer's separate API identity."""
    if receipt.get("export"):
        vrf = VRF.objects.get(pk=receipt["export"]["vrf"])
        if (
            vrf.tenant_id != receipt["tenant"]
            or not vrf.enforce_unique
            or vrf.description != "Bearings observed network " + data["key"]
        ):
            raise ValueError("Retained export VRF policy changed")
        field = CustomField.objects.get(name="bearings_inventory")
        if field.type != "json":
            raise ValueError("Retained inventory field changed")
        return receipt
    if not data.get("export_inventory") or data.get("verify_only"):
        return receipt
    name = "Bearings observed network " + data["key"]
    if VRF.objects.filter(description=name).exists():
        raise ValueError("Unrecorded export VRF exists; reconcile explicitly")
    vrf = VRF.objects.create(
        name="CIRCL agent inventory", tenant_id=receipt["tenant"], enforce_unique=True, description=name
    )
    field, _ = CustomField.objects.get_or_create(
        name="bearings_inventory", defaults={"type": "json", "label": "Bearings reported inventory"}
    )
    if field.type != "json":
        raise ValueError("Existing inventory custom field has an incompatible type")
    field.object_types.add(
        ContentType.objects.get_for_model(Device), ContentType.objects.get_for_model(VirtualMachine)
    )
    identity = CustomField.objects.get(name="bearings_id", type="text")
    identity.object_types.add(
        *[ContentType.objects.get_for_model(m) for m in (Interface, VMInterface, IPAddress)]
    )
    for model, constraint in [
        (Interface, {"device__tenant_id": receipt["tenant"]}),
        (VMInterface, {"virtual_machine__tenant_id": receipt["tenant"]}),
        (IPAddress, {"tenant_id": receipt["tenant"], "vrf_id": vrf.pk}),
        (VRF, {"id": vrf.pk}),
    ]:
        permission = ObjectPermission.objects.create(
            name="Bearings export " + data["key"] + " " + model.__name__,
            actions=["view"] if model == VRF else ["view", "add", "change"],
            constraints=constraint,
        )
        permission.object_types.add(ContentType.objects.get_for_model(model))
        permission.users.add(receipt["user"])
    return {
        **receipt,
        "export": {"inventory": True, "vrf": vrf.pk},
        "permissions": permissions(receipt["user"]),
    }


if __name__ == "__main__":
    print(json.dumps(manage(json.load(sys.stdin))))
