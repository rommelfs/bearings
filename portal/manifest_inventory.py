"""Project new manifest observations without adopting an existing manual version."""

from django.db.models import Q
from django.core.exceptions import ValidationError
from .agent_freshness import recent_component
from .models import Installation, Product
from .access import audit
from .product_matching import ensure_watch

MISP_CPE = "cpe:2.3:a:misp:misp:*:*:*:*:*:*:*:*"


def product_identifier(component):
    if component.manifest.get("method") == "misp-version-json":
        return MISP_CPE
    declared = component.manifest.get("identifier")
    if declared:
        return declared
    import re
    from urllib.parse import quote

    name = re.sub(r"[^a-z0-9._+-]+", "-", component.name.casefold()).strip("-")[:120] or "application"
    profile = component.key.split(":")[1]
    return "pkg:generic/" + name + "?profile=" + quote(profile, safe="")


def compatible(product, component):
    same_name = product.name.casefold() == component.name.casefold()
    if component.manifest.get("identifier") or component.manifest.get("method") == "misp-version-json":
        return product.identifier == product_identifier(component) or (not product.identifier and same_name)
    return product.identifier == product_identifier(component) or same_name


def project(device):
    # Caller holds device/source locks. Explicit rollout software permission
    # allows creation; manual/CSV records always require explicit binding.
    if not device.auto_software:
        return 0
    candidates = device.components.filter(
        recent_component(),
        manager="manifest",
        installation__isnull=True,
        inventory_excluded=False,
        missing_since__isnull=True,
    ).order_by("pk")[:16]
    count = 0
    for component in candidates:
        if component.manifest.get("method") not in {
            "misp-version-json",
            "file-regex",
            "json-fields",
            "git-tag",
        }:
            continue
        identifier = product_identifier(component)
        if (
            device.components.filter(
                manager="manifest", installation__isnull=False, manifest__path=component.manifest["path"]
            )
            .exclude(pk=component.pk)
            .exists()
        ):
            continue
        existing = Installation.objects.filter(
            asset_id=device.asset_id, product__organization_id=device.organization_id
        ).filter(Q(product__identifier=identifier) | Q(product__name__iexact=component.name))
        # Other independent manifest instances can coexist. Never overwrite a
        # manually maintained installation or an installation owned elsewhere.
        if existing.exclude(agent_component__manager="manifest").exists():
            continue
        product, _ = Product.objects.get_or_create(
            organization_id=device.organization_id, name=component.name, identifier=identifier
        )
        installation = Installation.objects.create(
            asset_id=device.asset_id, product=product, version=component.version
        )
        component.installation = installation
        component.automatic_installation = True
        component.save(update_fields=["installation", "automatic_installation"])
        try:
            ensure_watch(product)
        except ValidationError:
            # Retain inventory if the operator's configured intelligence source
            # needs correction. Discovery exposes the monitoring coverage gap.
            pass
        count += 1
        audit(
            None,
            device.organization,
            "agent.application_inventoried",
            component.pk,
            method=component.manifest["method"],
            installation=installation.pk,
        )
    return count
