"""Explicit native managed-inventory capability; capture JSON privately, never log tokens."""

import json
import sys
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from dcim.models import Device, DeviceType, DeviceRole, Manufacturer, Site
from extras.models import CustomField, Tag
from users.models import ObjectPermission, Token
from virtualization.models import VirtualMachine
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
        return receipt

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
    return {
        **receipt,
        "managed": True,
        "permissions": permissions(receipt["user"]),
        "defaults": {"site": site.pk, "role": role.pk, "device_type": dtype.pk, "virtualization_tags": tags},
    }


if __name__ == "__main__":
    print(json.dumps(manage(json.load(sys.stdin))))
