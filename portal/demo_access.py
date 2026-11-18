"""Narrow only the explicitly managed bundled demonstration account, never general memberships."""

import os
from urllib.parse import urlsplit
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from .access import audit, is_analyst, require
from .demo_data import KEY
from .models import DemoDataset, DemoObject, InventorySource, Membership


@transaction.atomic
def scope_company_admin(actor, config):
    require(actor.is_active and actor.is_superuser)
    if not settings.DEBUG or os.getenv("BEARINGS_DEV_STACK") != "1" or config.get("mode") != "bundled":
        raise ValidationError(
            "The single-company fixture profile requires the explicit bundled development lab"
        )
    user = get_user_model().objects.filter(username="company-admin", is_active=True).first()
    if not user:
        return 0
    if user.is_superuser or user.is_staff or is_analyst(user):
        raise ValidationError(
            "Unexpected operator privileges on company-admin; preserve them for manual review"
        )
    eligible = set()
    preferred = None
    for item in config["connections"]:
        if urlsplit(item["base_url"]).hostname != "netbox.bearings.test":
            raise ValidationError("Refusing a non-lab inventory source")
        source = (
            InventorySource.objects.select_related("instance")
            .filter(organization__slug=item["organization_slug"])
            .first()
        )
        if (
            not source
            or source.mode != "central"
            or not source.instance
            or source.instance.base_url != item["base_url"]
            or source.instance.token_env_var != item["token_env_var"]
            or source.tenant_id != item.get("tenant_id")
        ):
            raise ValidationError("Bundled inventory identity does not match; no membership changed")
        eligible.add(source.organization_id)
        if item["access_mode"] == "read_write":
            preferred = source.organization_id
    dataset = DemoDataset.objects.select_for_update().filter(key=KEY, state="active").first()
    if dataset:
        owned_orgs = list(
            DemoObject.objects.filter(dataset=dataset, model_label="portal.organization").values_list(
                "object_pk", flat=True
            )
        )
        eligible.update(
            InventorySource.objects.filter(
                organization_id__in=owned_orgs, mode="development", instance=None
            ).values_list("organization_id", flat=True)
        )
    legacy = InventorySource.objects.filter(
        organization__slug="example-labs", mode="development", instance=None
    ).first()
    if legacy:
        eligible.add(legacy.organization_id)
    grants = list(Membership.objects.select_for_update().filter(user=user).order_by("pk"))
    if any(grant.organization_id not in eligible for grant in grants):
        raise ValidationError("Unrelated or converted company grants preserved; manual review required")
    if not grants:
        return 0  # Do not restore an explicitly revoked account membership.
    target = next((grant for grant in grants if grant.organization_id == preferred), grants[0])
    removed = [grant for grant in grants if grant.pk != target.pk]
    for grant in removed:
        audit(actor, grant.organization, "development.company_grant_removed", user.pk)
    ids = [str(grant.pk) for grant in removed]
    DemoObject.objects.filter(model_label="portal.membership", object_pk__in=ids).delete()
    Membership.objects.filter(pk__in=ids).delete()
    if removed:
        audit(
            actor,
            None,
            "development.single_company_profile",
            user.pk,
            organization=target.organization_id,
            removed=len(removed),
        )
    return len(removed)
