"""Executed inside our bundled NetBox only; synthetic data and scoped API users."""

import json
import os
import uuid
from pathlib import Path
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from users.models import User, Token, ObjectPermission
from tenancy.models import Tenant
from dcim.models import (
    Site,
    Manufacturer,
    DeviceType,
    DeviceRole,
    Device,
    Interface,
    Location,
    Rack,
    Platform,
)
from virtualization.models import VirtualMachine, VMInterface
from ipam.models import Prefix, IPAddress
from extras.models import CustomField

SECRETS = Path("/run/bearings/secrets")
NETBOX_SECRETS = Path("/run/secrets")


def enrich_asset(asset, tenant, site, suffix, kind):
    """Fill empty synthetic fixture facts only; preserve operator edits and API capabilities."""
    if asset.tenant_id != tenant.pk or asset.name != f"lab-{suffix}-{kind}" or asset.site_id != site.pk:
        return
    platform, _ = Platform.objects.get_or_create(
        slug="bearings-debian", defaults={"name": "Debian 12 (SYNTHETIC)"}
    )
    if not asset.platform_id:
        asset.platform = platform
    if isinstance(asset, Device):
        room, _ = Location.objects.get_or_create(
            site=site,
            slug="bearings-" + suffix,
            defaults={"name": f"Infrastructure room {suffix.upper()} (SYNTHETIC)"},
        )
        rack, _ = Rack.objects.get_or_create(
            site=site,
            name=f"LAB-{suffix.upper()}-01 (SYNTHETIC)",
            defaults={"location": room, "tenant": tenant, "u_height": 42},
        )
        if not asset.rack_id and not asset.location_id and asset.position is None:
            if rack.location_id != room.pk or rack.tenant_id != tenant.pk:
                raise RuntimeError("Synthetic rack changed; refusing to overwrite operator placement")
            asset.location, asset.rack, asset.position, asset.face = room, rack, 10, "front"
        if not asset.serial:
            asset.serial = f"SYNTHETIC-{suffix.upper()}-0001"
        if not asset.asset_tag:
            asset.asset_tag = f"LAB-{suffix.upper()}-SERVER-01"
        interface, _ = Interface.objects.get_or_create(
            device=asset, name="lab-mgmt0", defaults={"type": "virtual"}
        )
    else:
        interface, _ = VMInterface.objects.get_or_create(virtual_machine=asset, name="lab-mgmt0")
    number = 20 if kind == "server" else 21
    ipv4 = ("192.0.2." if suffix == "rw" else "198.51.100.") + str(number) + "/24"
    ipv6 = f"2001:db8:{10 if suffix == 'rw' else 20}::{number}/64"
    dns = f"lab-{suffix}-{kind}.infra.example.invalid"
    for field, address in [("primary_ip4", ipv4), ("primary_ip6", ipv6)]:
        if getattr(asset, field + "_id"):
            continue
        ip, _ = IPAddress.objects.get_or_create(
            tenant=tenant, address=address, vrf=None, defaults={"dns_name": dns}
        )
        ct = ContentType.objects.get_for_model(type(interface))
        if (
            ip.assigned_object_id is not None
            and (ip.assigned_object_type_id != ct.pk or ip.assigned_object_id != interface.pk)
        ) or ip.dns_name != dns:
            raise RuntimeError("Synthetic address ownership/DNS changed; existing data preserved")
        ip.assigned_object = interface
        ip.full_clean()
        ip.save()
        setattr(asset, field, ip)
    asset.full_clean()
    asset.save()


@transaction.atomic
def main():
    password = (SECRETS / "demo_password").read_text().strip()
    admin, created = User.objects.get_or_create(username="netbox-admin", defaults={"is_superuser": True})
    if created:
        admin.set_password(password)
        admin.save()
    site, _ = Site.objects.get_or_create(slug="bearings-lab", defaults={"name": "Bearings synthetic lab"})
    vendor, _ = Manufacturer.objects.get_or_create(
        slug="bearings-synthetic", defaults={"name": "Synthetic devices"}
    )
    dtype, _ = DeviceType.objects.get_or_create(
        slug="bearings-demo-server",
        defaults={"manufacturer": vendor, "model": "Synthetic server", "u_height": 1},
    )
    role, _ = DeviceRole.objects.get_or_create(
        slug="bearings-demo", defaults={"name": "Synthetic server", "color": "4caf50"}
    )
    custom, _ = CustomField.objects.get_or_create(
        name="bearings_id", defaults={"type": "text", "label": "Bearings asset identity"}
    )
    custom.object_types.add(
        ContentType.objects.get_for_model(Device), ContentType.objects.get_for_model(VirtualMachine)
    )
    configs = []
    for suffix, access, write_enabled, network in [
        ("rw", "read_write", True, "192.0.2.0/24"),
        ("ro", "read_only", False, "198.51.100.0/24"),
    ]:
        tenant, _ = Tenant.objects.get_or_create(
            slug="bearings-" + suffix, defaults={"name": "Bearings synthetic " + suffix.upper()}
        )
        service, created = User.objects.get_or_create(username="bearings-api-" + suffix)
        if created:
            service.set_unusable_password()
            service.save()
        scoped, _ = ObjectPermission.objects.get_or_create(
            name="Bearings lab inventory " + suffix,
            defaults={
                "actions": ["view", "add"] if write_enabled else ["view"],
                "constraints": {"tenant_id": tenant.pk},
            },
        )
        scoped.object_types.add(
            *(
                ContentType.objects.get_for_model(model)
                for model in [Device, VirtualMachine, Prefix, IPAddress]
            )
        )
        scoped.users.add(service)
        taxonomy, _ = ObjectPermission.objects.get_or_create(
            name="Bearings lab reference data " + suffix, defaults={"actions": ["view"]}
        )
        taxonomy.object_types.add(
            *(
                ContentType.objects.get_for_model(model)
                for model in [
                    Site,
                    Location,
                    Rack,
                    Platform,
                    DeviceRole,
                    DeviceType,
                    Manufacturer,
                    Tenant,
                    CustomField,
                ]
            )
        )
        taxonomy.users.add(service)
        raw = (NETBOX_SECRETS / ("api_raw_" + suffix)).read_text().strip()
        token = Token.objects.filter(user=service, description="Bearings lab " + suffix).first()
        if token is None:
            token = Token(
                user=service, token=raw, description="Bearings lab " + suffix, write_enabled=write_enabled
            )
            token.save()
        elif not token.validate(raw):
            raise RuntimeError(
                "Bundled token and secret volume differ; investigate instead of replacing credentials"
            )
        value = token.get_auth_header_prefix().removeprefix("Bearer ") + raw
        variable = "NETBOX_BUNDLED_" + suffix.upper() + "_TOKEN"
        path = SECRETS / variable
        path.write_text(value + "\n")
        path.chmod(0o600)
        os.chown(path, int((SECRETS / "app_uid").read_text()), 0)
        assets = []
        for model, kind in [(Device, "server"), (VirtualMachine, "vm")]:
            key = str(uuid.uuid5(uuid.NAMESPACE_URL, "bearings-development/" + suffix + "/" + kind))
            defaults = {
                "name": "lab-" + suffix + "-" + kind,
                "tenant": tenant,
                "site": site,
                "status": "active",
                "custom_field_data": {"bearings_id": key},
            }
            if model is Device:
                defaults.update({"role": role, "device_type": dtype})
            asset, _ = model.objects.get_or_create(custom_field_data__bearings_id=key, defaults=defaults)
            enrich_asset(asset, tenant, site, suffix, kind)
            assets.append(
                {
                    "id": key,
                    "external_id": str(asset.pk),
                    "object_type": "dcim.device" if model is Device else "virtualization.virtualmachine",
                    "kind": kind,
                }
            )
        Prefix.objects.get_or_create(prefix=network, tenant=tenant)
        IPAddress.objects.get_or_create(address=network.replace("0/24", "10/24"), tenant=tenant)
        configs.append(
            {
                "name": "bundled-netbox-" + suffix,
                "organization_slug": "netbox-lab-" + suffix,
                "organization_name": "NetBox lab " + suffix.upper() + " (SYNTHETIC)",
                "base_url": "https://netbox.bearings.test",
                "browser_url": os.environ["BEARINGS_NETBOX_BROWSER_URL"],
                "token_env_var": variable,
                "auth_scheme": "Bearer",
                "access_mode": access,
                "tenant_id": tenant.pk,
                "allow_private": True,
                "site_id": site.pk,
                "role_id": role.pk,
                "device_type_id": dtype.pk,
                "assets": assets,
            }
        )
    config = SECRETS / "connections.json"
    config.write_text(json.dumps({"mode": "bundled", "connections": configs}))
    config.chmod(0o644)
    print(
        "Synthetic NetBox tenants, scoped read-only/read-write users and inventory provisioned; no credentials logged."
    )


main()
