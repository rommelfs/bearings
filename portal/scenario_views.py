from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from .access import require, organization
from .connectors.http import ConnectorError
from .intelligence import digest, resolve_risk, link_resolved_risk
from .issues import editable, link_risk, visible_issues
from .models import AssetIssue
from .scenario_suggestions import catalog_suggestions, draft_scenario


class ConfirmationForm(forms.Form):
    risk = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    reviewed_revision = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    reviewed_draft = forms.CharField(max_length=64, widget=forms.HiddenInput)
    reason = forms.CharField(
        max_length=4000,
        widget=forms.Textarea(attrs={"rows": 5}),
        label="Review the suggested justification and its assumptions",
    )


def confirm(actor, issue, candidate, values):
    require(actor.is_active and editable(actor, issue) and visible_issues(actor).filter(pk=issue.pk).exists())
    if values["reviewed_draft"] != draft_scenario(issue)["fingerprint"]:
        raise ValidationError("Issue or source evidence changed. Review the updated draft before confirming.")
    revision = resolve_risk(candidate.source_id, candidate.uuid)
    if revision.pk != values["reviewed_revision"]:
        raise ValidationError("The catalog scenario changed. Review the updated preview before confirming.")
    with transaction.atomic():
        issue = (
            AssetIssue.objects.select_for_update(of=("self",))
            .select_related("asset", "finding__record", "finding__installation")
            .get(pk=issue.pk)
        )
        require(editable(actor, issue) and visible_issues(actor).filter(pk=issue.pk).exists())
        if values["reviewed_draft"] != draft_scenario(issue)["fingerprint"]:
            raise ValidationError(
                "Issue or source evidence changed. Review the updated draft before confirming."
            )
        if not any(row["risk"].pk == candidate.pk for row in catalog_suggestions(issue)):
            raise ValidationError(
                "This catalog suggestion is no longer available. Review the current suggestions."
            )
        if issue.finding_id:
            link_resolved_risk(
                actor,
                issue.finding,
                revision,
                values["reason"],
                expected_evidence_hash=digest(issue.finding.record.payload),
            )
        else:
            link_risk(actor, issue, revision.risk, values["reason"])


@login_required
def automatic(request, slug, pk):
    org = organization(request, slug)
    issue = get_object_or_404(visible_issues(request.user), organization=org, pk=pk)
    draft = draft_scenario(issue)
    candidates = catalog_suggestions(issue, draft)
    can_confirm = editable(request.user, issue)
    selected = None
    selection = request.POST.get("risk") if request.method == "POST" else request.GET.get("risk")
    form = ConfirmationForm(request.POST if request.method == "POST" else None)
    if selection:
        try:
            selected = next((row["risk"] for row in candidates if row["risk"].pk == int(selection)), None)
        except ValueError:
            selected = None
        if selected is None:
            if request.method == "POST":
                form.add_error(None, "Choose one of the current catalog suggestions.")
            else:
                messages.warning(request, "Choose one of the current catalog suggestions.")
        elif request.method == "GET" and not selected.current_revision_id:
            # Fetch public details only after an explicit preview selection, never on dashboard reads.
            require(can_confirm)
            try:
                resolve_risk(selected.source_id, selected.uuid)
                selected.refresh_from_db()
            except ConnectorError:
                messages.error(
                    request,
                    "Catalog details are unavailable. The local draft and existing mappings are retained.",
                )
    if request.method == "POST":
        require(can_confirm)
        if form.is_valid() and selected:
            try:
                confirm(request.user, issue, selected, form.cleaned_data)
            except (ValidationError, ConnectorError) as exc:
                form.add_error(
                    None,
                    exc
                    if isinstance(exc, ValidationError)
                    else "Catalog verification failed; no mapping was created. Retry after checking source health.",
                )
                selected.refresh_from_db()
            else:
                messages.success(
                    request,
                    "Suggested scenario confirmed with pinned evidence. Company likelihood and impact still require assessment.",
                )
                return redirect("business-risk", slug=slug, pk=issue.pk)
    if selected and selected.current_revision_id:
        if not form.is_bound:
            form = ConfirmationForm(
                initial={
                    "risk": selected.pk,
                    "reviewed_revision": selected.current_revision_id,
                    "reviewed_draft": draft["fingerprint"],
                    "reason": draft["reason"],
                }
            )
        else:
            # A failed confirmation must show the newly reviewed context before the next submit.
            form.data = form.data.copy()
            form.data["reviewed_revision"] = selected.current_revision_id
            form.data["reviewed_draft"] = draft["fingerprint"]
    return render(
        request,
        "portal/automatic_scenario.html",
        {
            "org": org,
            "issue": issue,
            "draft": draft,
            "candidates": candidates,
            "selected": selected,
            "scenario": selected.current_revision.payload
            if selected and selected.current_revision_id
            else None,
            "form": form,
            "editable": can_confirm,
        },
    )
