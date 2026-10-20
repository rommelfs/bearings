"""Explicit synthetic human identities; scoped read-only permissions, no API service-key reuse."""

import json
from pathlib import Path
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from users.models import User, ObjectPermission
from dcim.models import Device
from virtualization.models import VirtualMachine
from ipam.models import IPAddress, Prefix
from tenancy.models import Tenant
from social_django.models import UserSocialAuth
from bearings_oidc import identity_uid

with transaction.atomic():
    manifest = json.loads(Path("/run/bearings/secrets/oidc-lab.json").read_text())
    for name in ["company-admin", "circl-analyst"]:
        user, created = User.objects.get_or_create(username="sso-" + name)
        if created:
            user.set_unusable_password()
            user.save()
            scopes = ["rw"] if name == "company-admin" else ["rw", "ro"]
            for suffix in scopes:
                tenant = Tenant.objects.get(slug="bearings-" + suffix)
                permission, new = ObjectPermission.objects.get_or_create(
                    name="SSO synthetic inventory " + suffix,
                    defaults={"actions": ["view"], "constraints": {"tenant_id": tenant.pk}},
                )
                if new:
                    permission.object_types.add(
                        *(
                            ContentType.objects.get_for_model(model)
                            for model in [Device, VirtualMachine, IPAddress, Prefix]
                        )
                    )
                permission.users.add(user)
        uid = identity_uid(manifest["issuer"], manifest["users"][name])
        existing = UserSocialAuth.objects.filter(provider="oidc", uid=uid).first()
        if not created and existing is None:
            print("Existing unbound NetBox SSO name retained without creating an identity link.")
            continue
        if existing and existing.user_id != user.pk:
            raise RuntimeError("SSO identity collision; operator intervention required")
        UserSocialAuth.objects.get_or_create(
            provider="oidc",
            uid=uid,
            defaults={
                "user": user,
                "extra_data": {
                    "issuer": manifest["issuer"],
                    "subject": manifest["users"][name],
                    "enabled": True,
                    "generation": "initial-synthetic-binding",
                },
            },
        )
print("Synthetic NetBox SSO identities prepared; existing permissions and accounts retained.")
