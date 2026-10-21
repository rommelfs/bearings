"""Explicit synthetic provenance, a read-only removal plan, and fail-closed local cleanup."""

from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import ipaddress
import json
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.db.models.signals import post_save
from django.utils import timezone
from .access import audit, require
from .models import AuditEvent, DemoDataset, DemoObject

KEY = "explore-v1"
CURRENT = ContextVar("bearings_demo_dataset", default=None)


@contextmanager
def capture(dataset):
    """Record creations only in this seed context, including service-created revisions."""
    token = CURRENT.set(dataset.pk)

    def created(sender, instance, created, **kwargs):
        if (
            CURRENT.get() == dataset.pk
            and created
            and sender._meta.app_label == "portal"
            and sender not in {DemoDataset, DemoObject, AuditEvent}
        ):
            DemoObject.objects.create(
                dataset=dataset, model_label=sender._meta.label_lower, object_pk=str(instance.pk)
            )

    post_save.connect(created, weak=False)
    try:
        yield
    finally:
        post_save.disconnect(created)
        CURRENT.reset(token)


def owned(dataset, *, lock=False):
    groups = defaultdict(set)
    for label, pk in dataset.entries.values_list("model_label", "object_pk"):
        groups[apps.get_model(label)].add(str(pk))
    for model in sorted(groups, key=lambda model: model._meta.label):
        rows = model.objects.filter(pk__in=groups[model]).order_by("pk")
        if lock:
            rows = rows.select_for_update()
        groups[model] = {str(pk) for pk in rows.values_list("pk", flat=True)}
    # Reviews of synthetic evidence remain synthetic; root business records are never inferred.
    for label, field in [
        ("IssueRevision", "issue"),
        ("IssueHistory", "issue"),
        ("FindingHistory", "finding"),
        ("SourceRecordRevision", "record"),
    ]:
        model = apps.get_model("portal", label)
        parent = model._meta.get_field(field).related_model
        if groups.get(parent):
            rows = model.objects.filter(**{field + "_id__in": groups[parent]})
            if lock:
                rows = rows.select_for_update()
            groups[model].update(str(value) for value in rows.values_list("pk", flat=True))
    return groups


def documentation_address(value):
    try:
        address = ipaddress.ip_interface(value).ip
        return any(
            address in ipaddress.ip_network(prefix)
            for prefix in ["192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "2001:db8::/32"]
        )
    except (TypeError, ValueError):
        return False


def removal_plan(dataset, *, lock=False):
    groups = owned(dataset, lock=lock)
    blockers = []
    for model in apps.get_models(include_auto_created=True):
        if model in {DemoObject, DemoDataset, AuditEvent}:
            continue
        for field in model._meta.fields:
            if (
                not field.is_relation
                or not (field.many_to_one or field.one_to_one)
                or not groups.get(field.related_model)
            ):
                continue
            rows = model.objects.filter(**{field.attname + "__in": groups[field.related_model]})
            if model._meta.auto_created:
                # A grant to a real organization must not disappear along with a fixture source.
                for other in model._meta.fields:
                    if other is field or not other.is_relation:
                        continue
                    count = rows.exclude(
                        **{other.attname + "__in": groups.get(other.related_model, set())}
                    ).count()
                    if count:
                        blockers.append(
                            f"{model._meta.label}.{other.name}: {count} unowned M2M endpoints (preserved)"
                        )
                continue
            unexpected = rows.exclude(pk__in=groups.get(model, set()))
            count = unexpected.count()
            if count:
                blockers.append(f"{model._meta.label}.{field.name}: {count} unowned references (preserved)")
    contact = apps.get_model("portal", "Contact")
    if groups.get(contact) and any(
        not email.lower().endswith(".invalid")
        for email in contact.objects.filter(pk__in=groups[contact]).values_list("email", flat=True)
    ):
        blockers.append("Contact: non-synthetic recipient requires separate review")
    asset = apps.get_model("portal", "Asset")
    if groups.get(asset):
        for data in asset.objects.filter(pk__in=groups[asset]).values_list("upstream_data", flat=True):
            if (
                not isinstance(data, dict)
                or data.get("fixture") is not True
                or any(
                    not documentation_address(data[field])
                    for field in ["primary_ip4", "primary_ip6"]
                    if data.get(field)
                )
            ):
                blockers.append(
                    "Asset: replaced fixture/provenance or non-documentation address requires separate review"
                )
                break
    claim = apps.get_model("portal", "InfrastructureClaim")
    if groups.get(claim):
        for kind, value in claim.objects.filter(pk__in=groups[claim]).values_list("kind", "value"):
            if not (
                (kind == "domain" and value.endswith(".invalid"))
                or (kind == "ip" and documentation_address(value))
            ):
                blockers.append("InfrastructureClaim: changed synthetic scope requires separate review")
                break
    # A fixture promoted to a live connector is no longer eligible for automatic removal.
    source = apps.get_model("portal", "InventorySource")
    if (
        groups.get(source)
        and source.objects.filter(pk__in=groups[source]).exclude(mode="development", instance=None).exists()
    ):
        blockers.append("InventorySource: promoted live inventory requires separate review")
    for label in ["RTInstance", "FlowIntelInstance", "MOSPSource"]:
        model = apps.get_model("portal", label)
        if groups.get(model) and model.objects.filter(pk__in=groups[model], enabled=True).exists():
            blockers.append(f"{label}: enabled live connector requires separate review")
    source = apps.get_model("portal", "PlumInstance")
    if groups.get(source) and source.objects.filter(pk__in=groups[source], fixture=False).exists():
        blockers.append("PlumInstance: converted live source requires separate review")
    for label in ["RTTicket", "FlowIntelCase"]:
        model = apps.get_model("portal", label)
        if groups.get(model) and model.objects.filter(pk__in=groups[model]).exclude(remote_id=None).exists():
            blockers.append(f"{label}: exported backend identities require separate retention/cleanup review")
    receipt = apps.get_model("portal", "NotificationReceipt")
    delivery = apps.get_model("portal", "NotificationDelivery")
    if groups.get(delivery) and receipt.objects.filter(delivery_id__in=groups[delivery]).exists():
        blockers.append("Notification receipts/outbox artifacts require separate retention review")
    manifest = sorted((m._meta.label_lower, sorted(ids)) for m, ids in groups.items())
    fingerprint = hashlib.sha256(json.dumps(manifest).encode()).hexdigest()
    return {
        "dataset": dataset.key,
        "state": dataset.state,
        "counts": {
            m._meta.label: len(ids) for m, ids in sorted(groups.items(), key=lambda row: row[0]._meta.label)
        },
        "total": sum(map(len, groups.values())),
        "organizations": list(
            apps.get_model("portal", "Organization")
            .objects.filter(pk__in=groups.get(apps.get_model("portal", "Organization"), []))
            .order_by("name")
            .values("name", "slug")
        ),
        "blockers": sorted(set(blockers)),
        "fingerprint": fingerprint,
    }, groups


@transaction.atomic
def purge(actor, key, fingerprint):
    require(actor.is_active and actor.is_superuser)
    dataset = DemoDataset.objects.select_for_update().get(key=key)
    plan, groups = removal_plan(dataset, lock=True)
    if plan["fingerprint"] != fingerprint:
        raise ValidationError("Demo contents changed; request a fresh removal preview")
    if plan["blockers"]:
        raise ValidationError("Cleanup blocked: " + "; ".join(plan["blockers"]))
    org = apps.get_model("portal", "Organization")
    # Keep the audit trail after removing its synthetic organization.
    AuditEvent.objects.filter(organization_id__in=groups.get(org, [])).update(organization=None)
    risk = apps.get_model("portal", "MOSPRisk")
    risk.objects.filter(pk__in=groups.get(risk, [])).update(current_revision=None)
    ticket = apps.get_model("portal", "RTTicket")
    ticket.objects.filter(pk__in=groups.get(ticket, []), role="investigation").delete()
    pending = dict(groups)
    while pending:
        progress = False
        for model, ids in list(pending.items()):
            try:
                with transaction.atomic():
                    model.objects.filter(pk__in=ids).delete()
            except ProtectedError:
                continue
            del pending[model]
            progress = True
        if not progress:
            raise ValidationError("Protected relationships changed; no demo data was removed")
    dataset.entries.all().delete()
    dataset.state, dataset.removed_at = "removed", timezone.now()
    dataset.save(update_fields=["state", "removed_at"])
    audit(actor, None, "demo.purged", key, counts=plan["counts"], fingerprint=fingerprint)
    return plan


def unmanaged_fixtures():
    """Legacy fixtures are reported, never adopted/deleted by matching a name."""
    from .models import Organization, PlumInstance, SourceRecord

    def registered(label):
        # Explicit values let each target PK field prepare its own int/UUID type on PostgreSQL.
        return list(DemoObject.objects.filter(model_label=label).values_list("object_pk", flat=True))

    candidates = Organization.objects.filter(slug__in=["example-labs", "exchange-example"]).exclude(
        pk__in=registered("portal.organization")
    )
    fixtures = (
        SourceRecord.objects.filter(source__startswith="fixture://")
        .exclude(pk__in=registered("portal.sourcerecord"))
        .count()
    )
    plum = PlumInstance.objects.filter(fixture=True).exclude(pk__in=registered("portal.pluminstance")).count()
    return {
        "legacy_organizations": candidates.count(),
        "unregistered_fixture_evidence": fixtures,
        "unregistered_plum_sources": plum,
    }
