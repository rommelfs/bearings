"""Operator-reviewed account/source plan for the explicitly isolated bundled SSO lab."""

import json
import uuid
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.crypto import salted_hmac
from social_django.models import UserSocialAuth
from config.oidc import identity_uid
from .access import audit, require, is_analyst
from .models import InfrastructureRegistration, InventorySource, NetBoxInstance, Organization


def plan(actor, username, netbox=True):
    require(actor.is_active and actor.is_superuser)
    user = get_user_model().objects.get(username=username)
    require(user.is_active and not user.is_staff and not user.is_superuser and not is_analyst(user))
    item = InfrastructureRegistration.objects.select_related("organization").get(
        user=user, status="approved", organization__operator_visibility=True
    )
    require(item.organization.membership_set.filter(user=user, role="admin").exists())
    source = InventorySource.objects.select_related("instance").get(organization=item.organization)
    marker = item.pk.hex.upper()
    variable = "NETBOX_COMPANY_" + marker + "_TOKEN"
    if netbox and not (
        (source.mode == "manual" and not source.instance_id and not source.asset_set.exists())
        or (
            source.mode == "central"
            and source.instance
            and source.instance.organization_id == item.organization_id
            and source.instance.token_env_var == variable
            and source.instance.base_url == "https://netbox.bearings.test"
            and source.instance.enabled
            and source.instance.access_mode == "read_write"
        )
    ):
        raise ValidationError(
            "NetBox enrollment needs empty company-reported inventory or this company's retained managed NetBox source. Existing inventory/source bindings require a separately reviewed migration; use --without-netbox for SSO only."
        )
    bindings = list(user.social_auth.filter(provider="oidc"))
    if len(bindings) > 1 or any(
        not b.extra_data.get("enabled") or b.extra_data.get("issuer") != settings.SSO_ISSUER for b in bindings
    ):
        raise ValidationError(
            "Existing/revoked identity bindings require operator review; no binding restored."
        )
    data = {
        "registration": str(item.pk),
        "organization": item.organization_id,
        "organization_slug": item.organization.slug,
        "company_name": item.company_name,
        "misp_org_uuid": str(item.organization.misp_org_uuid) if item.organization.misp_org_uuid else None,
        "username": user.username,
        "email": item.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email_verified": bool(item.email_verified_at),
        "issuer": settings.SSO_ISSUER,
        "source": str(source.pk),
        "source_mode": source.mode,
        "source_instance": str(source.instance_id) if source.instance_id else None,
        "netbox": netbox,
        "token_env_var": variable,
        "subject": bindings[0].extra_data.get("subject") if bindings else None,
    }
    data["fingerprint"] = salted_hmac("company-sso-plan", json.dumps(data, sort_keys=True)).hexdigest()
    return data


@transaction.atomic
def finalize(actor, original, idp, native=None):
    require(actor.is_active and actor.is_superuser)
    org = Organization.objects.select_for_update().get(pk=original["organization"])
    source = InventorySource.objects.select_for_update(nowait=True).get(organization=org)
    current = plan(actor, original["username"], original["netbox"])
    if current["fingerprint"] != original["fingerprint"]:
        raise ValidationError(
            "Company/user/source changed during provisioning. Existing data retained; review and retry."
        )
    if idp["issuer"] != settings.SSO_ISSUER or not idp.get("subject"):
        raise ValidationError("Identity provider mismatch")
    user = get_user_model().objects.select_for_update().get(username=original["username"])
    uid = identity_uid(settings.SSO_ISSUER, idp["subject"])
    binding = UserSocialAuth.objects.select_for_update().filter(provider="oidc", uid=uid).first()
    if binding and (binding.user_id != user.pk or not binding.extra_data.get("enabled")):
        raise ValidationError("Identity is revoked or belongs to another account; preserved")
    if original["netbox"]:
        if (
            not native
            or native["registration"] != original["registration"]
            or native["subject"] != idp["subject"]
        ):
            raise ValidationError("Native company identity does not match")
        instance, created = NetBoxInstance.objects.get_or_create(
            token_env_var=original["token_env_var"],
            defaults={
                "name": "Company " + original["registration"],
                "organization": org,
                "base_url": "https://netbox.bearings.test",
                "browser_url": native["browser_url"],
                "auth_scheme": "Bearer",
                "access_mode": "read_write",
                "allow_private": True,
                "site_id": native["site"],
                "role_id": native["role"],
                "device_type_id": native["device_type"],
            },
        )
        if not created and (
            instance.organization_id != org.pk
            or not instance.enabled
            or instance.access_mode != "read_write"
            or instance.base_url != "https://netbox.bearings.test"
            or instance.site_id != native["site"]
            or instance.role_id != native["role"]
            or instance.device_type_id != native["device_type"]
            or instance.auth_scheme != "Bearer"
            or instance.browser_url != native["browser_url"]
        ):
            raise ValidationError("Retained source policy differs; no policy changed")
        if source.mode == "manual":
            # Explicitly reviewed empty-source conversion, after rechecking under its writer lock.
            require(not source.asset_set.exists() and source.instance_id is None)
            source.mode, source.instance, source.tenant_id = "central", instance, native["tenant"]
            source.import_enabled, source.import_requested = True, True
            source.full_clean()
            source.save()
        else:
            require(source.instance_id == instance.pk and source.tenant_id == native["tenant"])
    if not binding:
        binding = UserSocialAuth.objects.create(
            user=user,
            provider="oidc",
            uid=uid,
            extra_data={
                "issuer": settings.SSO_ISSUER,
                "subject": idp["subject"],
                "enabled": True,
                "generation": str(uuid.uuid4()),
                "last_verified": 0,
                "onboarding_registration": original["registration"],
            },
        )
    audit(actor, org, "sso.company_enrolled", user.pk, identity=uid, netbox=bool(native))
    return {
        "registration": original["registration"],
        "organization": org.pk,
        "subject": idp["subject"],
        "issuer": settings.SSO_ISSUER,
        "username": user.username,
        "source": str(source.pk),
        "netbox": native,
    }
