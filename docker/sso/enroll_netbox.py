"""Run under the explicit bundled operator job; tenant-constrained human and API identities."""

import json
from itertools import product
import os
import secrets
import uuid
from pathlib import Path
from django.db import transaction
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from users.models import User, Token, ObjectPermission
from tenancy.models import Tenant
from dcim.models import (
    Device,
    Site,
    Interface,
    InventoryItem,
    Rack,
    Location,
    DeviceRole,
    DeviceType,
    Manufacturer,
)
from virtualization.models import VirtualMachine, VMInterface
from ipam.models import IPAddress, Prefix, VRF
from social_django.models import UserSocialAuth
from bearings_oidc import identity_uid

ROOT = Path("/run/bearings/secrets")


def private(path, value):
    descriptor = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(value)
    os.chmod(path, 0o600)
    os.chown(path, int((ROOT / "app_uid").read_text()), 0)


def provision(data):
    config = json.loads((ROOT / "connections.json").read_text())
    manifest = json.loads((ROOT / "oidc-lab.json").read_text())
    if (
        config["mode"] != "bundled"
        or data["issuer"] != manifest["issuer"]
        or any(c["base_url"] != "https://netbox.bearings.test" for c in config["connections"])
    ):
        raise ValueError("Non-lab source or issuer")
    key = uuid.UUID(data["registration"]).hex
    path = ROOT / ("company-sso-" + key + ".json")
    native_name = "company-" + key
    if path.exists():
        saved = json.loads(path.read_text())
        if saved["subject"] != data["subject"] or saved["registration"] != data["registration"]:
            raise ValueError("Retained identity mismatch")
        tenant = Tenant.objects.get(pk=saved["tenant"])
        site = Site.objects.get(pk=saved["site"])
        if (
            tenant.slug != "bearings-company-" + key
            or tenant.description != "Bearings registration " + data["registration"]
            or site.tenant_id != tenant.pk
        ):
            raise ValueError("Retained tenant/site identity changed")
        human = User.objects.get(pk=saved["user"])
        service = User.objects.get(pk=saved["service"])
        if (
            not human.is_active
            or human.is_superuser
            or human.groups.exists()
            or human.username != native_name
            or human.has_usable_password()
            or not service.is_active
            or service.is_superuser
            or service.groups.exists()
        ):
            raise ValueError("Retained account policy changed")
        for profile, user in [("human_permissions", human), ("service_permissions", service)]:
            expected = saved[profile]
            perms = list(ObjectPermission.objects.filter(users=user).order_by("pk"))
            actual = [
                {
                    "id": p.pk,
                    "actions": p.actions,
                    "constraints": p.constraints,
                    "types": sorted(p.object_types.values_list("pk", flat=True)),
                    "enabled": p.enabled,
                }
                for p in perms
            ]
            if actual != expected:
                raise ValueError("Retained permissions changed; no grant restored")
        raw = (ROOT / (data["token_env_var"] + ".raw")).read_text().strip()
        token = Token.objects.get(pk=saved["token"], user=service)
        if (
            not token.write_enabled
            or not token.validate(raw)
            or (getattr(token, "expires", None) and token.expires <= timezone.now())
        ):
            raise ValueError("Retained API token disabled or changed")
        if data["phase"] == "identity":
            uid = identity_uid(data["issuer"], data["subject"])
            binding = UserSocialAuth.objects.filter(provider="oidc", uid=uid).first()
            if binding and (binding.user_id != human.pk or not binding.extra_data.get("enabled")):
                raise ValueError("Native identity revoked or reassigned")
            UserSocialAuth.objects.get_or_create(
                provider="oidc",
                uid=uid,
                defaults={
                    "user": human,
                    "extra_data": {
                        "issuer": data["issuer"],
                        "subject": data["subject"],
                        "enabled": True,
                        "generation": str(uuid.uuid4()),
                        "onboarding_registration": data["registration"],
                    },
                },
            )
        return saved
    if (
        data["phase"] != "prepare"
        or User.objects.filter(username=native_name).exists()
        or User.objects.filter(username=native_name + "-api").exists()
    ):
        raise ValueError("Unknown/unowned native identity; no adoption by name")
    slug = "bearings-company-" + key
    if Tenant.objects.filter(slug=slug).exists():
        raise ValueError("Unowned tenant retained")
    with transaction.atomic():
        display_name = data["company_name"][:70] + " · " + key[:8]
        tenant = Tenant.objects.create(
            name=display_name, slug=slug, description="Bearings registration " + data["registration"]
        )
        site = Site.objects.create(name=display_name, slug=slug, tenant=tenant)
        manufacturer = Manufacturer.objects.create(name="Company " + key, slug=slug)
        dtype = DeviceType.objects.create(manufacturer=manufacturer, model="Company device", slug=slug)
        role = DeviceRole.objects.create(name="Company " + key, slug=slug)
        human = User.objects.create(
            username=native_name,
            first_name=data["first_name"],
            last_name=data["last_name"],
            email=data["email"],
        )
        human.set_unusable_password()
        human.save()
        service = User.objects.create(username=native_name + "-api")
        service.set_unusable_password()
        service.save()

        def bounded(model, fixed, optional=()):
            allowed = {key.split("__")[0].removesuffix("_id") for key in fixed}
            allowed.update(name for name, _ in optional)
            # Unmanaged nullable relations cannot expose foreign reference objects.
            defaults = {
                field.name + "_id__isnull": True
                for field in model._meta.fields
                if field.is_relation
                and field.null
                and not field.name.startswith("_")
                and field.name not in allowed
            }
            choices = [[{name + "_id__isnull": True}, condition] for name, condition in optional]
            return [
                {**defaults, **fixed, **{k: v for choice in combination for k, v in choice.items()}}
                for combination in product(*choices)
            ]

        device = bounded(
            Device,
            {"tenant_id": tenant.pk, "site_id": site.pk, "device_type_id": dtype.pk, "role_id": role.pk},
            [
                ("rack", {"rack__tenant_id": tenant.pk, "rack__site_id": site.pk}),
                ("location", {"location__site_id": site.pk}),
                ("primary_ip4", {"primary_ip4__tenant_id": tenant.pk}),
                ("primary_ip6", {"primary_ip6__tenant_id": tenant.pk}),
                ("oob_ip", {"oob_ip__tenant_id": tenant.pk}),
            ],
        )
        vm = bounded(
            VirtualMachine,
            {"tenant_id": tenant.pk, "site_id": site.pk},
            [
                ("primary_ip4", {"primary_ip4__tenant_id": tenant.pk}),
                ("primary_ip6", {"primary_ip6__tenant_id": tenant.pk}),
            ],
        )
        ips = []
        for assignment in [
            {"assigned_object_id__isnull": True},
            {"interface__device__tenant_id": tenant.pk},
            {"vminterface__virtual_machine__tenant_id": tenant.pk},
        ]:
            for constraint in bounded(
                IPAddress,
                {
                    "tenant_id": tenant.pk,
                    "assigned_object_type_id__in": [
                        None,
                        ContentType.objects.get_for_model(Interface).pk,
                        ContentType.objects.get_for_model(VMInterface).pk,
                    ],
                },
                [
                    ("vrf", {"vrf__tenant_id": tenant.pk}),
                    ("nat_inside", {"nat_inside__tenant_id": tenant.pk}),
                ],
            ):
                # assigned-object NULL has no type; keep it separate from interface assignments.
                if "assigned_object_id__isnull" in assignment:
                    constraint.pop("assigned_object_type_id__in", None)
                    constraint["assigned_object_type_id__isnull"] = True
                ips.append({**constraint, **assignment})
        specs = [
            ([Device], device),
            ([VirtualMachine], vm),
            ([IPAddress], ips),
            (
                [Prefix],
                bounded(
                    Prefix,
                    {"tenant_id": tenant.pk, "scope_type_id__isnull": True, "scope_id__isnull": True},
                    [("vrf", {"vrf__tenant_id": tenant.pk})],
                ),
            ),
            ([Rack], bounded(Rack, {"tenant_id": tenant.pk, "site_id": site.pk})),
            ([VRF], bounded(VRF, {"tenant_id": tenant.pk})),
            (
                [Interface],
                bounded(
                    Interface,
                    {
                        "device__tenant_id": tenant.pk,
                        "tagged_vlans__isnull": True,
                        "vdcs__isnull": True,
                        "wireless_lans__isnull": True,
                    },
                    [("vrf", {"vrf__tenant_id": tenant.pk})],
                ),
            ),
            (
                [InventoryItem],
                bounded(
                    InventoryItem,
                    {"device__tenant_id": tenant.pk, "component_id__isnull": True},
                    [("manufacturer", {"manufacturer_id": manufacturer.pk})],
                ),
            ),
            (
                [VMInterface],
                bounded(
                    VMInterface,
                    {"virtual_machine__tenant_id": tenant.pk, "tagged_vlans__isnull": True},
                    [("vrf", {"vrf__tenant_id": tenant.pk})],
                ),
            ),
            ([Location], bounded(Location, {"site_id": site.pk})),
        ]
        for index, (models, constraint) in enumerate(specs):
            for label, user, actions in [
                ("human", human, ["view", "add", "change"]),
                ("service", service, ["view", "add"]),
            ]:
                permission = ObjectPermission.objects.create(
                    name=f"Company {key} {label} {index}", actions=actions, constraints=constraint
                )
                permission.object_types.add(*(ContentType.objects.get_for_model(model) for model in models))
                permission.users.add(user)
        for model, constraint in [
            (Tenant, {"id": tenant.pk}),
            (Site, {"id": site.pk}),
            (Manufacturer, {"id": manufacturer.pk}),
            (DeviceType, {"id": dtype.pk}),
            (DeviceRole, {"id": role.pk}),
        ]:
            permission = ObjectPermission.objects.create(
                name=f"Company {key} reference {model.__name__}", actions=["view"], constraints=constraint
            )
            permission.object_types.add(ContentType.objects.get_for_model(model))
            permission.users.add(human, service)
        raw = secrets.token_urlsafe(48)
        token = Token(user=service, token=raw, description="Bearings company " + key, write_enabled=True)
        token.save()
        saved = {
            "registration": data["registration"],
            "username": native_name,
            "subject": data["subject"],
            "user": human.pk,
            "service": service.pk,
            "tenant": tenant.pk,
            "site": site.pk,
            "role": role.pk,
            "device_type": dtype.pk,
            "token": token.pk,
            "browser_url": "https://localhost:" + str(manifest["ports"]["netbox"]),
        }
        for profile, user in [("human_permissions", human), ("service_permissions", service)]:
            saved[profile] = [
                {
                    "id": p.pk,
                    "actions": p.actions,
                    "constraints": p.constraints,
                    "types": sorted(p.object_types.values_list("pk", flat=True)),
                    "enabled": p.enabled,
                }
                for p in ObjectPermission.objects.filter(users=user).order_by("pk")
            ]
        private(ROOT / (data["token_env_var"] + ".raw"), raw + "\n")
        value = token.get_auth_header_prefix().removeprefix("Bearer ") + raw
        private(ROOT / data["token_env_var"], value + "\n")
    private(path, json.dumps(saved))
    return saved


def main(data):
    # DB host guard prevents this operator job from running against an independent installation.
    if os.getenv("DB_HOST") != "netbox-db" or not os.getenv("BEARINGS_SSO_LAB") == "1":
        raise ValueError("Bundled SSO lab required")
    return provision(data)
