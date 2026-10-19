"""Explicit bundled-only fixture placement. Run by scripts/dev.py, not at startup."""

import os
import uuid
from decimal import Decimal
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from dcim.models import Device, Interface, Location, Rack, Site
from dcim.models import Platform
from ipam.models import IPAddress
from tenancy.models import Tenant


@transaction.atomic
def main(marker):
    if os.getenv("DB_HOST") != "netbox-db":
        raise RuntimeError("Exchange location fixture requires the bundled NetBox database")
    uuid.UUID(marker)
    tenant = Tenant.objects.get(slug="bearings-rw")
    device = Device.objects.select_for_update().get(tenant=tenant, custom_field_data__bearings_id=marker)
    if device.name != "exchange-example-01 (SYNTHETIC)" or device.site.slug not in {
        "bearings-lab",
        "bearings-exchange-dc",
    }:
        raise RuntimeError("Example identity/site changed; operator data preserved")
    site, _ = Site.objects.get_or_create(
        slug="bearings-exchange-dc", defaults={"name": "Luxembourg DC (SYNTHETIC)"}
    )
    room, _ = Location.objects.get_or_create(
        site=site, slug="exchange-room", defaults={"name": "Messaging room M1 (SYNTHETIC)"}
    )
    rack, _ = Rack.objects.get_or_create(
        site=site, name="EX-01 (SYNTHETIC)", defaults={"location": room, "tenant": tenant, "u_height": 42}
    )
    if (
        rack.location_id != room.pk
        or rack.tenant_id != tenant.pk
        or device.rack_id not in {None, rack.pk}
        or device.location_id not in {None, room.pk}
    ):
        raise RuntimeError("Example rack/location changed; operator data preserved")
    if device.face not in {None, "", "front"}:
        raise RuntimeError("Example rack face changed; operator data preserved")
    if device.position is not None and device.position != Decimal("22"):
        raise RuntimeError("Example rack unit changed; operator data preserved")
    platform, _ = Platform.objects.get_or_create(
        slug="bearings-exchange-windows", defaults={"name": "Windows Server (SYNTHETIC)"}
    )
    if device.platform_id not in {None, platform.pk}:
        raise RuntimeError("Example platform changed; operator data preserved")
    interface, _ = Interface.objects.get_or_create(
        device=device, name="example-mgmt0", defaults={"type": "virtual"}
    )
    address_ids = []
    for address in ["192.0.2.25/24", "2001:db8::25/64"]:
        ip, _ = IPAddress.objects.get_or_create(
            tenant=tenant,
            address=address,
            vrf=None,
            defaults={"dns_name": "exchange-01.mail.example.invalid"},
        )
        interface_type = ContentType.objects.get_for_model(Interface)
        if ip.assigned_object_id is not None and (
            ip.assigned_object_type_id != interface_type.pk or ip.assigned_object_id != interface.pk
        ):
            raise RuntimeError("Example address already belongs to another object; preserved")
        if ip.dns_name != "exchange-01.mail.example.invalid":
            raise RuntimeError("Example DNS name changed; preserved")
        ip.assigned_object = interface
        ip.full_clean()
        ip.save()
        address_ids.append(ip.pk)
    if device.primary_ip4_id not in {None, address_ids[0]} or device.primary_ip6_id not in {
        None,
        address_ids[1],
    }:
        raise RuntimeError("Example primary IP changed; preserved")
    device.site, device.location, device.rack, device.position, device.face = (
        site,
        room,
        rack,
        Decimal("22"),
        "front",
    )
    device.platform = platform
    device.primary_ip4_id, device.primary_ip6_id = address_ids
    device.full_clean()
    device.save()
    print(
        "Synthetic Exchange placement verified: example.invalid DNS, documentation IPv4/IPv6, Luxembourg DC / Messaging room M1 / Rack EX-01 / U22. No scans or credential changes."
    )


main(globals()["EXAMPLE_BEARINGS_ID"])
