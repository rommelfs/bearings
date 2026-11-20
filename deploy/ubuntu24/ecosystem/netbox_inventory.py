"""Native pilot provisioning; JSON stdin/stdout must be captured privately by the root helper."""

import json
import secrets
import sys
import uuid
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from dcim.models import Device
from ipam.models import IPAddress, Prefix
from tenancy.models import Tenant
from users.models import ObjectPermission, Token
from virtualization.models import VirtualMachine


def provision(data):
    key = uuid.UUID(data["key"]).hex
    User = get_user_model()
    User.objects.get(username=data["actor"], is_active=True, is_superuser=True)
    name = "bearings-inventory-" + key
    marker = "Bearings native inventory " + key
    saved = data.get("saved")
    if saved:
        user = User.objects.get(pk=saved["user"])
        tenant = Tenant.objects.get(pk=saved["tenant"])
        token = Token.objects.get(pk=saved["token_id"])
        raw = saved["raw"]
        if (
            user.username != name
            or not user.is_active
            or user.is_superuser
            or user.groups.exists()
            or user.user_permissions.exists()
            or user.has_usable_password()
            or tenant.slug != name
            or tenant.description != marker
            or token.user_id != user.pk
            or token.write_enabled
            or not token.is_active
            or not token.validate(raw)
        ):
            raise ValueError("Retained native credentials or tenant policy changed; no restoration")
        permissions = ObjectPermission.objects.filter(users=user).order_by("pk")
        actual = [
            {
                "id": p.pk,
                "actions": p.actions,
                "constraints": p.constraints,
                "enabled": p.enabled,
                "types": sorted(p.object_types.values_list("pk", flat=True)),
            }
            for p in permissions
        ]
        if actual != saved["permissions"]:
            raise ValueError("Retained native permissions changed; no restoration")
        return saved
    if User.objects.filter(username=name).exists() or Tenant.objects.filter(slug=name).exists():
        raise ValueError("Unrecorded native identity exists; reconcile without adopting by name")
    with transaction.atomic():
        tenant = Tenant.objects.create(name="CIRCL", slug=name, description=marker)
        user = User(username=name, is_active=True)
        user.set_unusable_password()
        user.save()
        policies = []
        for model, constraint in [
            (Device, {"tenant_id": tenant.pk}),
            (VirtualMachine, {"tenant_id": tenant.pk}),
            (IPAddress, {"tenant_id": tenant.pk}),
            (Prefix, {"tenant_id": tenant.pk}),
            (Tenant, {"id": tenant.pk}),
        ]:
            p = ObjectPermission.objects.create(
                name=name + " " + model.__name__, actions=["view"], constraints=constraint
            )
            p.object_types.add(ContentType.objects.get_for_model(model))
            p.users.add(user)
            policies.append(
                {
                    "id": p.pk,
                    "actions": p.actions,
                    "constraints": p.constraints,
                    "enabled": p.enabled,
                    "types": sorted(p.object_types.values_list("pk", flat=True)),
                }
            )
        raw = secrets.token_urlsafe(48)
        token = Token(
            user=user,
            token=raw,
            description=marker,
            write_enabled=False,
            expires=timezone.now() + timedelta(days=90),
        )
        token.save()
        return {
            "tenant": tenant.pk,
            "user": user.pk,
            "token_id": token.pk,
            "raw": raw,
            "value": token.get_auth_header_prefix().removeprefix("Bearer ") + raw,
            "permissions": policies,
        }


if __name__ == "__main__":
    print(json.dumps(provision(json.load(sys.stdin))))
