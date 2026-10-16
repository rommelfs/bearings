"""Executed inside our bundled NetBox only; synthetic data and scoped API users."""

import json
import os
import uuid
from pathlib import Path
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from users.models import User, Token, ObjectPermission
from tenancy.models import Tenant
from dcim.models import Site, Manufacturer, DeviceType, DeviceRole, Device
from virtualization.models import VirtualMachine
from ipam.models import Prefix, IPAddress
from extras.models import CustomField

SECRETS = Path("/run/bearings/secrets")
NETBOX_SECRETS = Path("/run/secrets")


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
                for model in [Site, DeviceRole, DeviceType, Manufacturer, Tenant, CustomField]
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
