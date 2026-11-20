"""Reviewed platform-only consolidation; unsupported source/identity conflicts fail closed."""

import hashlib
import json
import uuid
from django.apps import apps
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction, OperationalError
from django.db.models import Exists, OuterRef
from django.utils import timezone
from .access import audit, require
from .national_snapshots import DERIVED_MODELS
from .models import Organization, Membership, InventorySource, OrganizationInvitation

MOVERS = {"Contact", "InfrastructureClaim", "Asset", "Product", "SourceRecord", "Finding", "AssetIssue"}
RETAIN = {
    "AuditEvent",
    "Membership",
    "InventorySource",
    "InfrastructureRegistration",
    "InventoryReviewPolicy",
    "OrganizationLocation",
    "OrganizationConfiguration",
    "ConfigurationSection",
    "OrganizationInvitation",
}

# These fields report background work; they do not change the facts, identities,
# permissions or settings reviewed for transfer. Actual business rows stay pinned.
BACKGROUND_FIELDS = {
    "InventorySource": {
        "last_read_attempt",
        "last_read_success",
        "read_error",
        "last_attempt",
        "last_success",
        "error",
        "import_requested",
        "last_import_attempt",
        "last_import_success",
        "import_error",
        "import_summary",
    },
    "InventoryReviewPolicy": {"next_reminder_at"},
    "MISPInstance": {"last_attempt", "last_success", "error", "generation", "syncing_until"},
}


def plan(actor, source, target, retire_personal_misp=False):
    require(actor.is_active and actor.is_superuser)
    if source.pk == target.pk or source.merged_into_id or target.merged_into_id:
        raise ValidationError("Select two different active organizations")
    rows, blockers, state = [], [], []
    for org in (source, target):
        for relation in Organization._meta.related_objects:
            model = relation.related_model
            if model.__name__ in DERIVED_MODELS:
                continue  # Recomputable caches cannot block or invalidate a business-data preview.
            if relation.many_to_many:
                qs = model.objects.filter(**{relation.field.name: org})
            else:
                qs = model.objects.filter(**{relation.field.name: org.pk})
            count = qs.count()
            if count > 5000:
                blockers.append(f"{org.name}: {model.__name__} exceeds the 5,000-row reviewed merge limit")
                continue
            # Append-only audits remain archived; opening a detail page or worker
            # status updates must not invalidate an otherwise unchanged preview.
            # Fingerprints remain server-side, including protected credential policy.
            if model.__name__ != "AuditEvent":
                fields = [
                    field.attname
                    for field in model._meta.concrete_fields
                    if field.attname not in BACKGROUND_FIELDS.get(model.__name__, set())
                ]
                state.append((org.pk, model._meta.label, list(qs.order_by("pk").values(*fields))))
            personal_misp = model.__name__ == "MISPInstance" and retire_personal_misp
            if org.pk == source.pk and personal_misp and count:
                if qs.filter(syncing_until__gt=timezone.now()).exists():
                    blockers.append("MISP refresh is in progress; wait for it to finish and preview again")
                if (
                    qs.filter(organization__isnull=True).exists()
                    or qs.exclude(credential_kind="encrypted").exists()
                    or qs.filter(owner__isnull=True).exists()
                ):
                    blockers.append(
                        "Only personal encrypted MISP connections can be retired during this merge"
                    )
            if (
                org.pk == source.pk
                and count
                and model.__name__ not in MOVERS | RETAIN | {"Organization"}
                and not personal_misp
            ):
                blockers.append(
                    f"{org.display_label}: {model.__name__} requires separate reconciliation before merging"
                    + (
                        "; select the explicit personal-MISP retirement option to archive these connections"
                        if model.__name__ == "MISPInstance"
                        else ""
                    )
                )
            if org.pk == source.pk and count:
                rows.append(
                    {
                        "model": str(model._meta.verbose_name_plural).title(),
                        "count": count,
                        "handling": (
                            "Disable; retain key/cache on archive; owner reconnects"
                            if personal_misp
                            else "Keep target schedule, or copy source schedule if absent; renew review"
                            if model.__name__ == "InventoryReviewPolicy"
                            else "Transfer"
                            if model.__name__ in MOVERS
                            else "Combine; target role wins"
                            if model.__name__ == "Membership"
                            else "Revoke pending; retain history"
                            if model.__name__ == "OrganizationInvitation"
                            else "Retain on archived source"
                        ),
                    }
                )
        inv = InventorySource.objects.filter(organization=org).first()
        if (
            inv
            and (inv.mode != "manual" or inv.instance_id)
            and (org.pk == source.pk or source.assets.exists())
        ):
            blockers.append(
                f"{org.name}: only local manual inventory can be merged; reconcile native sources separately"
            )
    if (
        apps.get_model("portal", "InventoryWrite")
        .objects.filter(asset__organization=source, completed_at=None)
        .exists()
    ):
        blockers.append("Pending inventory writes must be reconciled before merging")
    if apps.get_model("portal", "CSVAssetBinding").objects.filter(source__organization=source).exists():
        blockers.append("Stable CSV source bindings require separate reconciliation")
    if source.assets.exclude(external_id="").exists():
        blockers.append("Source assets retain external identities; use a reviewed source migration")
    if source.merged_organizations.exists() or target.merged_organizations.exists():
        blockers.append("Existing archived merge histories require separate review before a further merger")
    for org in (source, target):
        if (
            apps.get_model("portal", "FlowIntelCase").objects.filter(finding__organization=org).exists()
            or apps.get_model("portal", "RTTicket").objects.filter(issue__organization=org).exists()
        ):
            blockers.append(f"{org.name}: native cases/tickets require separate reconciliation")
    config = getattr(source, "configuration", None)
    if config and any(
        [
            config.pgp_public_key,
            config.smime_certificate,
            config.ail_enabled,
            config.ail_keywords,
            config.ail_honeytokens,
            config.ail_notification_email,
        ]
    ):
        blockers.append("Source has communication/AIL configuration; reconcile it before merging")
    if source.configuration_sections.filter().exists():
        # Drafts may contain facts not yet projected into inventory.
        if any(s.draft for s in source.configuration_sections.all()):
            blockers.append("Source has configuration drafts; review and clear them before merging")
    if source.misp_org_uuid and source.misp_org_uuid != target.misp_org_uuid:
        blockers.append("Source MISP organization UUID differs; reconcile attested identity first")
    # Native product identity is not inferred by a name. Refuse collisions instead of losing evidence.
    Product = apps.get_model("portal", "Product")
    if (
        Product.objects.filter(organization=source)
        .filter(
            Exists(
                Product.objects.filter(
                    organization=target, name=OuterRef("name"), identifier=OuterRef("identifier")
                )
            )
        )
        .exists()
    ):
        blockers.append("Product identity collision; reconcile the duplicate products before merging")
    Record = apps.get_model("portal", "SourceRecord")
    if (
        Record.objects.filter(organization=source)
        .filter(
            Exists(
                Record.objects.filter(
                    organization=target, source=OuterRef("source"), external_id=OuterRef("external_id")
                )
            )
        )
        .exists()
    ):
        blockers.append("Evidence identity collision; reconcile source records before merging")
    overlap = []
    target_members = {m.user_id: m for m in target.membership_set.all()}
    for m in source.membership_set.select_related("user"):
        existing = target_members.get(m.user_id)
        if existing:
            overlap.append(
                {
                    "user": m.user.username,
                    "source": m.get_role_display(),
                    "target": existing.get_role_display(),
                    "result": existing.get_role_display(),
                }
            )
    if not (
        source.membership_set.filter(role="admin", user__is_active=True)
        .exclude(user_id__in=target.membership_set.values("user_id"))
        .exists()
        or target.membership_set.filter(role="admin", user__is_active=True).exists()
    ):
        blockers.append("The resulting company needs at least one active company administrator")
    state.extend(
        [
            list(Organization.objects.filter(pk__in=[source.pk, target.pk]).order_by("pk").values()),
            {"retire_personal_misp": bool(retire_personal_misp)},
        ]
    )
    digest = hashlib.sha256(json.dumps(state, sort_keys=True, default=str).encode()).hexdigest()
    return {
        "source": source,
        "target": target,
        "rows": rows,
        "overlap": overlap,
        "blockers": blockers,
        "digest": digest,
        "retire_personal_misp": bool(retire_personal_misp),
        "ticket": signing.dumps(
            {
                "source": source.pk,
                "target": target.pk,
                "digest": digest,
                "actor": actor.pk,
                "retire_personal_misp": bool(retire_personal_misp),
            },
            salt="company-merge",
        ),
    }


@transaction.atomic
def merge(actor, ticket):
    require(actor.is_active and actor.is_superuser)
    try:
        data = signing.loads(ticket, salt="company-merge", max_age=900)
    except signing.BadSignature:
        raise ValidationError("Merge preview expired; prepare a new preview") from None
    require(data["actor"] == actor.pk)
    from .models import NationalState

    list(
        NationalState.objects.select_for_update()
        .filter(organization_id__in=[data["source"], data["target"]])
        .order_by("organization_id")
    )
    orgs = {
        o.pk: o
        for o in Organization.objects.select_for_update()
        .filter(pk__in=[data["source"], data["target"]])
        .order_by("pk")
    }
    if len(orgs) != 2:
        raise ValidationError("Merge organizations changed")
    source, target = orgs[data["source"]], orgs[data["target"]]
    MISPInstance = apps.get_model("portal", "MISPInstance")
    ReviewPolicy = apps.get_model("portal", "InventoryReviewPolicy")
    try:
        # Worker publication can hold its source/policy while auditing the company.
        # Fail fast rather than wait in the reverse order and risk a deadlock.
        for model in (InventorySource, MISPInstance, ReviewPolicy):
            list(
                model.objects.select_for_update(nowait=True)
                .filter(organization__in=[source, target])
                .order_by("pk")
            )
    except OperationalError:
        raise ValidationError(
            "Inventory, MISP or review data is currently changing. Retry with a fresh merge preview."
        ) from None
    current = plan(actor, source, target, retire_personal_misp=data.get("retire_personal_misp", False))
    if current["blockers"] or current["digest"] != data["digest"]:
        raise ValidationError("Data or access changed, or conflicts remain. Prepare a new merge preview.")
    manifest = {
        name: [
            str(pk)
            for pk in apps.get_model("portal", name)
            .objects.filter(organization=source)
            .values_list("pk", flat=True)
        ]
        for name in sorted(MOVERS)
    }
    members_before = list(source.membership_set.values("user_id", "role"))
    visibility_before = {"source": source.operator_visibility, "target": target.operator_visibility}
    retired_misp = []
    if current["retire_personal_misp"]:
        retired_misp = list(MISPInstance.objects.filter(organization=source).values_list("pk", flat=True))
        MISPInstance.objects.filter(pk__in=retired_misp).update(
            enabled=False,
            generation=uuid.uuid4(),
            syncing_until=None,
            error="Company archived by reviewed merge; owner must reconnect under the retained company",
        )
    source_inventory = InventorySource.objects.filter(organization=source).first()
    target_inventory = InventorySource.objects.filter(organization=target).first()
    if source_inventory and not target_inventory:
        source_inventory.organization = target
        source_inventory.save(update_fields=["organization"])
        target_inventory = source_inventory
    if source.assets.exists() and not target_inventory:
        raise ValidationError("A target manual inventory source is required")
    if target_inventory:
        source.assets.update(source=target_inventory)
    for name in sorted(MOVERS):
        apps.get_model("portal", name).objects.filter(organization=source).update(organization=target)
    target_users = set(target.membership_set.values_list("user_id", flat=True))
    Membership.objects.bulk_create(
        [
            Membership(organization=target, user_id=m["user_id"], role=m["role"])
            for m in members_before
            if m["user_id"] not in target_users
        ]
    )
    source.membership_set.all().delete()
    OrganizationInvitation.objects.filter(organization=source, consumed_at=None, revoked_at=None).update(
        revoked_at=timezone.now()
    )
    # Existing company settings and CIRCL policy are not broadened by combining memberships.
    target.operator_visibility = source.operator_visibility and target.operator_visibility
    target.save(update_fields=["operator_visibility"])
    from .inventory_review import mandatory_review_mail

    mandatory_mail = mandatory_review_mail(source) or mandatory_review_mail(target)
    policy = ReviewPolicy.objects.select_for_update().filter(organization=target).first()
    original_policy = ReviewPolicy.objects.select_for_update().filter(organization=source).first()
    if not policy and original_policy:
        policy = ReviewPolicy.objects.create(
            organization=target,
            interval_days=original_policy.interval_days,
            reminder_days=original_policy.reminder_days,
            email_enabled=original_policy.email_enabled or mandatory_mail,
        )
    if policy:
        policy.next_due = timezone.localdate()
        policy.last_reviewed_at = None
        policy.last_reviewed_by = None
        policy.next_reminder_at = timezone.now()
        policy.email_enabled = policy.email_enabled or mandatory_mail
        policy.save(
            update_fields=[
                "next_due",
                "last_reviewed_at",
                "last_reviewed_by",
                "next_reminder_at",
                "email_enabled",
            ]
        )
    source.merged_into = target
    source.operator_visibility = False
    source.save(update_fields=["merged_into", "operator_visibility"])
    NationalState.objects.filter(organization__in=[source, target]).update(dirty=True)
    for name in DERIVED_MODELS - {"NationalState"}:
        apps.get_model("portal", name).objects.filter(organization__in=[source, target]).delete()
    audit(
        actor,
        target,
        "organization.merged",
        source.pk,
        target_org=target.pk,
        preview_digest=current["digest"],
        transferred=manifest,
        original_memberships=members_before,
        previous_visibility=visibility_before,
        retired_personal_misp=retired_misp,
    )
    return target
