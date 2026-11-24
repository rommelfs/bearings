"""Resumable company configuration using current owner authorization and explicit setup review."""

import hashlib
import json
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.db.models import Q
from django.utils import timezone
from .access import can_review_contact, require, audit
from .models import (
    OrganizationConfiguration,
    ConfigurationSection,
    InfrastructureClaim,
    InfrastructureRegistration,
    Organization,
)
from .configuration_forms import (
    ScopeConfigurationForm,
    InventoryConfigurationForm,
    MonitoringConfigurationForm,
    ContactConfigurationForm,
)

SECTIONS = (
    ("scope", "IPs, networks & domains", ScopeConfigurationForm),
    ("inventory", "Hardware & software", InventoryConfigurationForm),
    ("ail", "AIL monitoring preparation", MonitoringConfigurationForm),
    ("contacts", "Contacts & secure communication", ContactConfigurationForm),
)
FORMS = {key: form for key, _, form in SECTIONS}


def wizard_available(org):
    registration = InfrastructureRegistration.objects.filter(organization=org).first()
    return org.operator_visibility and (not registration or registration.status == "approved")


def current_claims(org):
    now = timezone.now()
    return org.claims.filter(status="declared", valid_from__lte=now).filter(
        Q(valid_until=None) | Q(valid_until__gt=now)
    )


def initial_data(org, section):
    profile = OrganizationConfiguration.objects.filter(organization=org).first()
    if section == "scope":
        data = {"networks": [], "ips": [], "domains": [], "network_context": ""}
        contexts = set()
        for claim in current_claims(org).order_by("pk"):
            key = "ips" if claim.kind == "ip" else "domains" if claim.kind == "domain" else "networks"
            data[key].append(claim.value)
            contexts.add(claim.network_context)
        data = {key: "\n".join(value) if isinstance(value, list) else value for key, value in data.items()}
        if len(contexts) == 1:
            data["network_context"] = contexts.pop()
        return data
    if section == "ail":
        return {
            "enabled": profile.ail_enabled if profile else False,
            "keywords": "\n".join(profile.ail_keywords) if profile else "",
            "honeytokens": "\n".join(profile.ail_honeytokens) if profile else "",
            "notification_email": profile.ail_notification_email if profile else "",
        }
    if section == "contacts":
        return {
            "postal_address": org.postal_address,
            "pgp_public_key": profile.pgp_public_key if profile else "",
            "smime_certificate": profile.smime_certificate if profile else "",
        }
    state = ConfigurationSection.objects.filter(organization=org, section=section).first()
    data = {"notes": state.draft.get("notes", "") if state else ""}
    if state:
        from .models import Asset, Installation

        asset = Asset.objects.filter(
            pk=state.draft.get("_asset_pk"), organization=org, source__organization=org, source__mode="manual"
        ).first()
        if asset:
            data.update(asset_name=asset.name, asset_kind=asset.kind)
            installation = (
                Installation.objects.filter(
                    pk=state.draft.get("_installation_pk"), asset=asset, product__organization=org
                )
                .select_related("product")
                .first()
            )
            if installation:
                data.update(
                    software_name=installation.product.name,
                    version=installation.version,
                    is_operating_system=installation.is_operating_system,
                )
    return data


def digest(org, section):
    return hashlib.sha256(json.dumps(initial_data(org, section), sort_keys=True).encode()).hexdigest()


def completion_error(org, section, data):
    if (
        section == "scope"
        and not org.claims.exclude(status__in=["expired", "disputed"])
        .filter(valid_from__lte=timezone.now())
        .filter(Q(valid_until=None) | Q(valid_until__gt=timezone.now()))
        .exists()
    ):
        return "Add at least one IP, network or domain before reviewing this section."
    if section == "inventory":
        from .models import Installation

        if not Installation.objects.filter(
            asset__organization=org,
            asset__source__organization=org,
            product__organization=org,
            asset__lifecycle="active",
            asset__missing_since=None,
        ).exists():
            return "Add an active asset and at least one software/OS record before reviewing this section. Unknown versions are allowed and remain a coverage gap."
    if section == "contacts" and not org.contacts.exclude(email="").exclude(emergency_phone="").exists():
        return "Add an emergency contact with email and emergency telephone before reviewing this section."
    return ""


def progress(org):
    states = {s.section: s for s in org.configuration_sections.all()}
    items = []
    for key, label, _ in SECTIONS:
        state = states.get(key)
        complete = bool(state and state.reviewed and not completion_error(org, key, initial_data(org, key)))
        items.append({"key": key, "label": label, "complete": complete})
    done = sum(item["complete"] for item in items)
    return {"items": items, "done": done, "total": len(items), "percent": done * 100 // len(items)}


def apply_section(actor, org, section, data, state):
    """Caller holds the organization/section lock. No network or upstream inventory writes."""
    require(can_review_contact(actor, org))
    if section == "scope":
        old = list(current_claims(org).select_for_update())
        contexts = {c.network_context for c in old}
        if len(old) > 100 or len(contexts) > 1:
            raise ValidationError(
                "Use individual scope editors for more than 100 declarations or multiple network contexts; existing declarations were preserved."
            )
        desired = {(item["kind"], item["value"], item["network_context"]) for item in data["scopes"]}
        existing = {(c.kind, c.value, c.network_context) for c in old}
        for claim in old:
            if (claim.kind, claim.value, claim.network_context) not in desired:
                claim.status = "expired"
                claim.valid_until = timezone.now()
                claim.save(update_fields=["status", "valid_until"])
                audit(actor, org, "scope.owner_withdrew", claim.pk)
        for kind, value, context in desired - existing:
            claim = InfrastructureClaim(organization=org, kind=kind, value=value, network_context=context)
            claim.full_clean()
            claim.save()
            audit(actor, org, "scope.created", claim.pk)
    elif section == "inventory" and data.get("asset_name"):
        from .models import Asset, Installation, Product, InventorySource, ProductWatch

        try:
            source = InventorySource.objects.select_for_update(nowait=True).get(organization=org)
        except DatabaseError as error:
            if getattr(error.__cause__, "sqlstate", None) == "55P03":
                raise ValidationError(
                    "Inventory is being updated. Your draft is retained; retry saving shortly."
                ) from None
            raise
        require(source.mode == "manual" and source.can_write)
        asset = (
            Asset.objects.select_for_update()
            .filter(pk=state.draft.get("_asset_pk"), organization=org, source=source)
            .first()
        )
        if not asset:
            asset = Asset(organization=org, source=source, state="recorded")
        asset.name, asset.kind = data["asset_name"], data.get("asset_kind") or "server"
        asset.full_clean()
        asset.save()
        state.draft["_asset_pk"] = str(asset.pk)
        if data.get("software_name"):
            product, _ = Product.objects.get_or_create(
                organization=org, name=data["software_name"], identifier=""
            )
            installation = (
                Installation.objects.select_for_update()
                .filter(pk=state.draft.get("_installation_pk"), asset=asset, product__organization=org)
                .first()
            )
            if not installation:
                installation = Installation(asset=asset)
            installation.product, installation.version = product, data["version"]
            installation.is_operating_system = data.get("is_operating_system", False)
            installation.full_clean()
            installation.save()
            state.draft["_installation_pk"] = installation.pk
            from .product_matching import ensure_watch

            try:
                ensure_watch(product, actor)
            except ValidationError:
                pass  # Product identity can remain unmapped; no applicability is inferred.
            ProductWatch.objects.filter(product=product).update(requested=True)
    elif section == "ail":
        profile, _ = OrganizationConfiguration.objects.get_or_create(organization=org)
        profile.ail_enabled = data["enabled"]
        profile.ail_keywords = data["keywords_list"]
        profile.ail_honeytokens = data["honeytokens_list"]
        profile.ail_notification_email = data["notification_email"]
        profile.save()
    elif section == "contacts":
        profile, _ = OrganizationConfiguration.objects.get_or_create(organization=org)
        profile.pgp_public_key = data["pgp_public_key"]
        profile.smime_certificate = data["smime_certificate"]
        profile.save()
        if org.postal_address != data["postal_address"]:
            org.postal_address = data["postal_address"]
            org.save(update_fields=["postal_address"])
    audit(actor, org, "configuration.saved", section)  # Never log keywords, Honeytokens or public-key bodies.


def locked_owner(user, org):
    current = Organization.objects.select_for_update().get(pk=org.pk)
    require(user.is_active and can_review_contact(user, current))
    return current


def ail_yara(org):
    """Offline custom-YARA handoff; never build a regex or enable an AIL notification."""
    state = ConfigurationSection.objects.filter(organization=org, section="ail").first()
    if state and state.draft.get("_invalid"):
        raise ValidationError("Correct the saved draft before exporting AIL rules.")
    profile = OrganizationConfiguration.objects.filter(organization=org).first()
    if not profile or not profile.ail_enabled or not (profile.ail_keywords or profile.ail_honeytokens):
        raise ValidationError(
            "Save at least one indicator and select manual AIL preparation before exporting."
        )
    rules = []
    for category, values in (("keywords", profile.ail_keywords), ("honeytokens", profile.ail_honeytokens)):
        if not values:
            continue
        lines = []
        for index, value in enumerate(values):
            # Encode UTF-8 bytes without allowing user input to escape a YARA literal.
            escaped = "".join(
                chr(b) if 32 <= b <= 126 and b not in {34, 92} else f"\\x{b:02x}"
                for b in value.encode("utf-8")
            )
            suffix = " nocase" if category == "keywords" else ""
            lines.append(f'        $i{index} = "{escaped}"{suffix}')
        rules.append(
            f"rule bearings_{org.pk}_{category} {{\n"
            '    meta:\n        purpose = "Manual review required; a match is not a confirmed leak"\n'
            f'        category = "{category}"\n    strings:\n'
            + "\n".join(lines)
            + "\n    condition:\n        any of them\n}"
        )
    return (
        "// Confidential company indicators. Import only into your approved AIL instance.\n\n"
        + "\n\n".join(rules)
        + "\n"
    )
