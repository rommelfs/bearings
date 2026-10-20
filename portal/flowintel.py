"""Reviewed private case hand-off. Writes are claimed before I/O; recovery reads never retry POSTs."""

import html
import re
import uuid
from datetime import timedelta
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction, IntegrityError
from django.utils import timezone
from .access import audit, can_operator_review, organizations_for, require
from .connectors.flowintel import api
from .connectors.http import ConnectorError
from .models import Finding, FlowIntelCase, FlowIntelInstance, FlowIntelTask
from .notifications import digest, finding_snapshot
from .presentation import ACTIVE_REVIEWS, vulnerability_summary

PLAYBOOK = [
    (
        "Validate installation and affectedness",
        "Review the installed edition/build and source evidence. Preserve unknown configuration and backport requirements.",
    ),
    (
        "Review and approve company notification",
        "Use Bearings contact eligibility, message preview and approval. This task does not send mail.",
    ),
    (
        "Agree remediation owner and patch window",
        "Assign an owner and a suitable patch window. This task performs no system changes.",
    ),
    (
        "Verify remediation evidence and follow up",
        "Record evidence in Bearings and explicitly review the finding. Completing this task does not resolve it automatically.",
    ),
]


def allowed(actor, finding):
    return bool(
        actor.is_active
        and finding.installation.asset.organization_id == finding.organization_id
        and finding.installation.product.organization_id == finding.organization_id
        and finding.installation.asset.source.organization_id == finding.organization_id
        and finding.record.organization_id == finding.organization_id
        and organizations_for(actor).filter(pk=finding.organization_id).exists()
        and finding.organization.operator_visibility
        and can_operator_review(actor, finding.organization)
        and finding.record.shareable
    )


def exportable(actor, finding):
    return (
        allowed(actor, finding)
        and finding.status in ACTIVE_REVIEWS
        and finding.analyst_applicability != "not_affected"
        and finding.installation.asset.lifecycle == "active"
    )


def finding_for(pk):
    return Finding.objects.select_related(
        "organization", "record", "installation__product", "installation__asset__source__instance"
    ).get(pk=pk)


def snapshot(finding, instance, deadline, reason):
    risks = []
    for link in (
        finding.risk_links.filter(withdrawn_at__isnull=True, evidence_revision__record_id=finding.record_id)
        .select_related("risk_revision__risk__source", "evidence_revision")
        .order_by("pk")[:30]
    ):
        risks.append(
            {
                "id": link.pk,
                "catalog_uuid": str(link.risk_revision.risk.uuid),
                "evidence_revision": link.evidence_revision_id,
                "risk_revision": link.risk_revision_id,
                "reason": link.reason,
            }
        )
    return {
        "finding": finding_snapshot(finding),
        "source_summary": vulnerability_summary(finding.record.payload),
        "risk_scenarios": risks,
        "deadline": deadline.isoformat() if deadline else None,
        "reason": reason,
        "bearings_url": instance.bearings_url,
        "service_org_id": instance.service_org_id,
    }


def description_for(data):
    # Fenced plain facts remain readable without interpreting source HTML/Markdown.
    import json

    facts = html.escape(data["finding"]["text"], quote=False)
    metadata = {key: value for key, value in data.items() if key != "finding"}
    metadata["evidence_hash"] = data["finding"]["evidence_hash"]
    text = facts + html.escape(json.dumps(metadata, indent=2, ensure_ascii=False), quote=False)
    fence = "`" * max(3, 1 + max((len(m) for m in re.findall(r"`+", text)), default=0))
    result = "Bearings evidence snapshot. CVSS is source severity; business risk remains unassessed. Product registration alone does not confirm affectedness.\n\n"
    result += fence + "text\n" + facts + "\n" + fence
    if data["bearings_url"]:
        result += "\n\n[Review finding in Bearings](" + data["bearings_finding_url"] + ")"
    result += (
        "\n\nEvidence references and source assessment:\n\n"
        + fence
        + "json\n"
        + html.escape(json.dumps(metadata, indent=2, ensure_ascii=False), quote=False)
        + "\n"
        + fence
    )
    return result


@transaction.atomic
def preview(actor, finding, instance, deadline, reason):
    finding = finding_for(finding.pk)
    instance = FlowIntelInstance.objects.get(pk=instance.pk)
    require(exportable(actor, finding) and instance.available)
    instance.full_clean()
    if not reason.strip() or len(reason) > 3000 or (deadline and deadline < timezone.localdate()):
        raise ValidationError("Provide a reason and a deadline today or later.")
    data = snapshot(finding, instance, deadline, reason.strip())
    binding, created = FlowIntelCase.objects.get_or_create(
        instance=instance,
        finding=finding,
        defaults={
            "creator": actor,
            "snapshot": data,
            "fingerprint": digest(data),
            "title": "",
            "description": "",
            "reason": reason.strip(),
            "deadline": deadline,
        },
    )
    binding = FlowIntelCase.objects.select_for_update().get(pk=binding.pk)
    if not created and (binding.attempted_at or binding.state not in {"draft", "blocked"}):
        return binding
    identifier = re.sub(r"[^A-Za-z0-9._-]", "-", finding.record.external_id)[:70]
    binding.title = f"Bearings {identifier} [{binding.pk}]"
    data["bearings_finding_url"] = (
        instance.bearings_url
        + f"/organizations/{finding.organization.slug}/intelligence/?finding={finding.pk}#finding-{finding.pk}"
    )
    # The URL contains only an operator-controlled origin and a generated scoped path.
    binding.snapshot = data
    binding.fingerprint = digest(data)
    binding.description = description_for(data)
    binding.creator, binding.deadline, binding.reason, binding.state, binding.error = (
        actor,
        deadline,
        reason.strip(),
        "draft",
        "",
    )
    binding.save()
    binding.tasks.all().delete()
    for step, (title, text) in enumerate(PLAYBOOK, 1):
        FlowIntelTask.objects.create(
            case=binding, step=step, title=f"{title} [{binding.pk}:{step}]", description=text
        )
    audit(
        actor,
        finding.organization,
        "flowintel.preview",
        binding.pk,
        instance=str(instance.pk),
        finding=finding.pk,
    )
    return binding


def current_snapshot(binding):
    data = snapshot(binding.finding, binding.instance, binding.deadline, binding.reason)
    data["bearings_finding_url"] = (
        binding.instance.bearings_url
        + f"/organizations/{binding.finding.organization.slug}/intelligence/?finding={binding.finding_id}#finding-{binding.finding_id}"
    )
    return data


def load(pk):
    binding = FlowIntelCase.objects.select_related("instance", "creator").get(pk=pk)
    binding.finding = finding_for(binding.finding_id)
    return binding


def require_write(binding):
    require(exportable(binding.creator, binding.finding) and binding.instance.available)
    if digest(current_snapshot(binding)) != binding.fingerprint:
        raise ValidationError(
            "Export evidence, asset, assessment or destination context changed. Review before further writes."
        )


@transaction.atomic
def approve(actor, pk):
    FlowIntelCase.objects.select_for_update().get(pk=pk)
    binding = load(pk)
    require(binding.creator_id == actor.pk and exportable(actor, binding.finding))
    if binding.state != "draft":
        raise ValidationError("This preview has already been approved or attempted.")
    require_write(binding)
    binding.state, binding.approved_at = "queued", timezone.now()
    binding.save(update_fields=["state", "approved_at"])
    audit(actor, binding.finding.organization, "flowintel.approved", binding.pk)
    return binding


def positive_id(value):
    if type(value) is not int or not 0 < value <= 2147483647:
        raise ConnectorError("Invalid FlowIntel identity")
    return value


def remote_case(binding):
    data = api(binding.instance, "GET", f"case/{positive_id(binding.remote_id)}")
    if not isinstance(data, dict):
        raise ConnectorError("Invalid FlowIntel case response")
    orgs = data.get("orgs")
    if (
        data.get("is_private") is not True
        or positive_id(data.get("owner_org_id")) != binding.instance.service_org_id
        or data.get("ticket_id") != str(binding.pk)
        or data.get("title") != binding.title
        or not isinstance(orgs, list)
        or len(orgs) != 1
        or type(orgs[0]) is not dict
        or positive_id(orgs[0].get("id")) != binding.instance.service_org_id
        or positive_id(data.get("id")) != binding.remote_id
    ):
        raise ConnectorError("FlowIntel case identity, privacy or organization scope changed")
    try:
        identity = uuid.UUID(data["uuid"])
    except (KeyError, ValueError, TypeError, AttributeError):
        raise ConnectorError("Invalid FlowIntel case UUID") from None
    if binding.remote_uuid and identity != binding.remote_uuid:
        raise ConnectorError("FlowIntel case UUID changed")
    if type(data.get("completed")) is not bool:
        raise ConnectorError("Invalid FlowIntel completion state")
    binding.remote_uuid = identity
    return data


def remote_tasks(binding):
    rows = []
    for route in ["tasks", "tasks_finished"]:
        data = api(binding.instance, "GET", f"case/{positive_id(binding.remote_id)}/{route}")
        if not isinstance(data, list) or len(data) > 200:
            raise ConnectorError("Invalid or excessive FlowIntel task list")
        rows.extend(data)
    seen = set()
    for task in rows:
        if (
            not isinstance(task, dict)
            or positive_id(task.get("id")) in seen
            or task.get("case_id") != binding.remote_id
            or type(task.get("completed")) is not bool
        ):
            raise ConnectorError("FlowIntel task identity or parent scope is invalid")
        seen.add(task["id"])
    return rows


@transaction.atomic
def claim(pk):
    FlowIntelCase.objects.select_for_update().get(pk=pk)
    binding = load(pk)
    if binding.state not in {"queued", "building"}:
        return None
    try:
        require_write(binding)
    except (PermissionDenied, ValidationError):
        binding.state, binding.error = (
            "blocked",
            "Current permission or export snapshot no longer permits writing.",
        )
        binding.save(update_fields=["state", "error"])
        audit(binding.creator, binding.finding.organization, "flowintel.blocked", binding.pk)
        return None
    task = None
    if binding.remote_id:
        task = binding.tasks.filter(state="pending").order_by("step").first()
        if task is None:
            binding.state = "linked"
            binding.save(update_fields=["state"])
            return None
        task.state = "creating"
        task.save(update_fields=["state"])
    binding.state = "working" if task else "creating"
    binding.attempted_at = binding.attempted_at or timezone.now()
    binding.last_attempt = timezone.now()
    binding.error = ""
    binding.save(update_fields=["state", "attempted_at", "last_attempt", "error"])
    audit(
        binding.creator,
        binding.finding.organization,
        "flowintel.write_claimed",
        binding.pk,
        step=task.step if task else 0,
    )
    return task.pk if task else 0


def process(pk):
    operation = claim(pk)
    if operation is None:
        return
    binding = load(pk)
    try:
        # Fresh permission/content/configuration check after the committed claim and before POST.
        require_write(binding)
        if operation == 0:
            payload = {
                "title": binding.title,
                "description": binding.description,
                "is_private": True,
                "ticket_id": str(binding.pk),
            }
            if binding.deadline:
                payload.update(deadline_date=binding.deadline.isoformat(), deadline_time="17-00")
            response = api(binding.instance, "POST", "case/create", payload=payload)
            binding.remote_id = positive_id(response.get("case_id") if isinstance(response, dict) else None)
            # Retain an acknowledged identity even if subsequent verification is unavailable.
            with transaction.atomic():
                binding.save(update_fields=["remote_id"])
            remote_case(binding)
            binding.save(update_fields=["remote_uuid"])
        else:
            remote_case(binding)
            require_write(load(pk))
            task = binding.tasks.get(pk=operation)
            payload = {"title": task.title, "description": task.description}
            if binding.deadline:
                payload.update(deadline_date=binding.deadline.isoformat(), deadline_time="17-00")
            response = api(binding.instance, "POST", f"case/{binding.remote_id}/create_task", payload=payload)
            task.remote_id = positive_id(response.get("task_id") if isinstance(response, dict) else None)
            task.state = "linked"
            task.save(update_fields=["state", "remote_id"])
        binding.state, binding.error = "building", ""
    except (ConnectorError, PermissionDenied, ValidationError, IntegrityError):
        binding.state, binding.error = (
            "uncertain",
            "Write outcome uncertain or verification blocked. Reconcile by reading; POST is not retried.",
        )
    binding.save(update_fields=["state", "error"])
    audit(
        binding.creator,
        binding.finding.organization,
        "flowintel.write_result",
        binding.pk,
        state=binding.state,
    )


def reconcile(pk, actor=None):
    binding = load(pk)
    actor = actor or binding.creator
    require(allowed(actor, binding.finding) and binding.instance.available)
    if (
        binding.state in {"creating", "working"}
        and binding.last_attempt
        and binding.last_attempt > timezone.now() - timedelta(minutes=2)
    ):
        raise ValidationError("A bounded write is still in progress. Wait before reconciling.")
    if not binding.attempted_at:
        raise ValidationError("There is no attempted hand-off to reconcile.")
    if not binding.remote_id:
        matches = []
        for route in ["all", "completed"]:
            response = api(binding.instance, "GET", f"case/{route}")
            rows = response.get("cases") if isinstance(response, dict) else None
            if not isinstance(rows, list) or len(rows) > 200:
                raise ConnectorError(
                    "Reconciliation list is too large or invalid; operator investigation required"
                )
            matches.extend(
                row
                for row in rows
                if isinstance(row, dict)
                and row.get("ticket_id") == str(binding.pk)
                and row.get("title") == binding.title
            )
        if len(matches) != 1:
            raise ConnectorError(
                "No unique matching case found. No POST was retried; operator investigation required"
            )
        binding.remote_id = positive_id(matches[0].get("id"))
    remote_case(binding)
    rows = remote_tasks(binding)
    with transaction.atomic():
        current = FlowIntelCase.objects.select_for_update().get(pk=pk)
        require(allowed(actor, finding_for(current.finding_id)))
        if (
            current.state in {"creating", "working"}
            and current.last_attempt
            and current.last_attempt > timezone.now() - timedelta(minutes=2)
        ):
            raise ValidationError("Write is still in progress.")
        for task in current.tasks.all():
            matches = [row for row in rows if row.get("title") == task.title]
            if len(matches) > 1:
                raise ConnectorError("Task correlation is ambiguous; operator investigation required")
            if task.remote_id:
                if len(matches) != 1 or matches[0]["id"] != task.remote_id:
                    raise ConnectorError("Linked task identity changed or disappeared")
            elif task.state == "creating" and not matches:
                # Absence is not proof that an interrupted POST never committed.
                raise ConnectorError("Task attempt remains uncertain. No task POST was retried.")
            elif matches:
                task.remote_id, task.state = matches[0]["id"], "linked"
                task.save(update_fields=["remote_id", "state"])
        current.remote_id, current.remote_uuid = binding.remote_id, binding.remote_uuid
        current.state = "building" if current.tasks.filter(state="pending").exists() else "linked"
        current.error = ""
        try:
            with transaction.atomic():
                current.save(update_fields=["remote_id", "remote_uuid", "state", "error"])
        except IntegrityError:
            raise ConnectorError(
                "Remote case identity is already bound; operator investigation required"
            ) from None
        audit(actor, binding.finding.organization, "flowintel.reconciled", current.pk)
    refresh(pk, actor)


def refresh(pk, actor=None):
    binding = load(pk)
    actor = actor or binding.creator
    require(allowed(actor, binding.finding) and binding.instance.available)
    if not binding.remote_id:
        raise ValidationError("Case identity has not been confirmed. Reconcile first.")
    FlowIntelCase.objects.filter(pk=pk).update(last_attempt=timezone.now())
    try:
        case = remote_case(binding)
        statuses = api(binding.instance, "GET", "case/list_status")
        if not isinstance(statuses, list) or len(statuses) > 100:
            raise ConnectorError("Invalid FlowIntel status dictionary")
        names = {
            row["id"]: str(row.get("name", ""))[:80]
            for row in statuses
            if isinstance(row, dict) and type(row.get("id")) is int
        }
        rows = remote_tasks(binding)
        tasks = []
        for task in binding.tasks.filter(remote_id__isnull=False).order_by("step"):
            matches = [row for row in rows if row["id"] == task.remote_id and row.get("title") == task.title]
            if len(matches) != 1:
                raise ConnectorError("Linked FlowIntel task is missing or changed")
            row = matches[0]
            tasks.append(
                {
                    "id": task.remote_id,
                    "title": PLAYBOOK[task.step - 1][0],
                    "completed": row["completed"],
                    "status": names.get(row.get("status_id"), "Unknown")
                    if type(row.get("status_id")) is int
                    else "Unknown",
                    "deadline": str(row.get("deadline") or "")[:80],
                }
            )
        summary = {
            "completed": case["completed"],
            "status": names.get(case.get("status_id"), "Unknown")
            if type(case.get("status_id")) is int
            else "Unknown",
            "deadline": str(case.get("deadline") or "")[:80],
            "tasks": tasks,
        }
        # Recheck current policy before retaining any newly read external data.
        require(allowed(actor, finding_for(binding.finding_id)))
        FlowIntelCase.objects.filter(pk=pk).update(
            summary=summary, remote_uuid=binding.remote_uuid, last_success=timezone.now(), error=""
        )
        audit(actor, binding.finding.organization, "flowintel.refreshed", binding.pk)
    except ConnectorError:
        FlowIntelCase.objects.filter(pk=pk).update(
            error="FlowIntel read failed or scope changed; last-known status retained."
        )
        raise
