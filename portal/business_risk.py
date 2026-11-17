"""Organization assessments use a documented local 5×5 matrix, not a MONARC score."""

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .access import audit, can_edit, can_operator_review, require, role_for
from .intelligence import digest, snapshot_evidence, link_state
from .issues import data_for, visible_issues, snapshot as issue_snapshot
from .models import AssetIssue, BusinessRiskRevision, Contact

LIKELIHOOD = [
    (1, "1 · Rare"),
    (2, "2 · Unlikely"),
    (3, "3 · Possible"),
    (4, "4 · Likely"),
    (5, "5 · Almost certain"),
]
IMPACT = [(1, "1 · Negligible"), (2, "2 · Minor"), (3, "3 · Material"), (4, "4 · Major"), (5, "5 · Critical")]


def scenarios(issue):
    if issue.finding_id:
        return [
            (f"cve:{link.pk}", link.risk_revision.risk.description, link)
            for link in issue.finding.risk_links.filter(withdrawn_at__isnull=True).select_related(
                "risk_revision__risk__source", "finding__record", "evidence_revision"
            )
        ]
    return [
        (f"issue:{link.pk}", link.risk_revision.risk.description, link)
        for link in issue.risk_scenarios.filter(withdrawn_at__isnull=True).select_related(
            "risk_revision__risk__source", "issue_revision"
        )
    ]


def evidence(issue):
    body = {
        "issue": data_for(issue),
        "asset": {
            "criticality": issue.asset.criticality,
            "lifecycle": issue.asset.lifecycle,
            "owner": issue.asset.responsible_contact_id,
            "team": issue.asset.responsible_team,
            "missing_since": str(issue.asset.missing_since or ""),
        },
        "scenarios": [],
    }
    if issue.finding_id:
        f = issue.finding
        body["finding"] = {
            "record": digest(f.record.payload),
            "assessment": f.analyst_applicability,
            "workflow": f.status,
            "applicability": f.applicability,
            "version": f.installation.version,
            "build": f.installation.build,
            "edition": f.installation.edition,
        }
    for key, _, link in scenarios(issue):
        body["scenarios"].append(
            {
                "key": key,
                "revision": link.risk_revision_id,
                "hash": link.risk_revision.content_hash,
                "current": link.risk_revision.risk.current_revision_id,
                "source_enabled": link.risk_revision.risk.source.enabled,
                "missing": str(link.risk_revision.risk.missing_since or ""),
                "reason": link.reason,
            }
        )
    return body


def band(score):
    return "Critical" if score >= 20 else "High" if score >= 12 else "Moderate" if score >= 5 else "Low"


class RiskAssessmentForm(forms.Form):
    previous_revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    reviewed_evidence = forms.CharField(max_length=64, widget=forms.HiddenInput)
    scenario = forms.ChoiceField(label="Linked MOSP / MONARC scenario")
    business_process = forms.CharField(max_length=250, label="Business service / process at risk")
    business_impact = forms.CharField(
        max_length=4000,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Consequences for this company (confidentiality, integrity, availability, legal/financial impact)",
    )
    assumptions = forms.CharField(
        max_length=4000,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Evidence, likelihood rationale and uncertainty",
    )
    likelihood = forms.TypedChoiceField(coerce=int, choices=[("", "Choose likelihood"), *LIKELIHOOD])
    impact = forms.TypedChoiceField(coerce=int, choices=[("", "Choose impact"), *IMPACT])
    existing_controls = forms.CharField(max_length=4000, widget=forms.Textarea(attrs={"rows": 3}))
    planned_measures = forms.CharField(
        max_length=4000, required=False, widget=forms.Textarea(attrs={"rows": 3})
    )
    residual_likelihood = forms.TypedChoiceField(
        coerce=int, choices=[("", "Choose residual likelihood"), *LIKELIHOOD]
    )
    residual_impact = forms.TypedChoiceField(coerce=int, choices=[("", "Choose residual impact"), *IMPACT])
    residual_rationale = forms.CharField(
        max_length=4000,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Why do the controls support this residual estimate? Distinguish planned from verified measures.",
    )
    decision = forms.ChoiceField(
        choices=[
            ("review", "Continue review"),
            ("mitigate", "Mitigate"),
            ("avoid", "Avoid"),
            ("transfer", "Transfer"),
            ("accept", "Accept risk (organization administrator)"),
        ]
    )
    owner = forms.ModelChoiceField(queryset=Contact.objects.none(), label="Accountable company contact")
    action_due = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}), label="Next action / review due"
    )
    acceptance_until = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    reason = forms.CharField(
        max_length=4000,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Reason for this assessment / decision",
    )

    def __init__(self, *args, issue, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["owner"].queryset = Contact.objects.filter(organization=issue.organization).order_by(
            "name"
        )
        self.fields["scenario"].choices = [(key, label) for key, label, _ in scenarios(issue)]

    def clean(self):
        values = super().clean()
        if values.get("decision") == "accept" and (
            not values.get("acceptance_until") or values["acceptance_until"] < timezone.localdate()
        ):
            self.add_error("acceptance_until", "Risk acceptance needs a current or future expiry date")
        if values.get("decision") in {"mitigate", "avoid", "transfer"} and not values.get("planned_measures"):
            self.add_error("planned_measures", "Describe the treatment measures and next action")
        return values


@transaction.atomic
def assess(actor, issue, values):
    issue = (
        AssetIssue.objects.select_for_update(of=("self",))
        .select_related("asset", "finding__record", "finding__installation")
        .get(pk=issue.pk)
    )
    require(
        actor.is_active
        and (can_edit(actor, issue.organization) or can_operator_review(actor, issue.organization))
    )
    require(visible_issues(actor).filter(pk=issue.pk).exists())
    form = RiskAssessmentForm(values, issue=issue)
    if not form.is_valid():
        raise ValidationError("Review the required assessment fields and company contact")
    values = form.cleaned_data
    latest = issue.business_risks.first()
    if values["previous_revision"] != (latest.pk if latest else 0) or values["reviewed_evidence"] != digest(
        evidence(issue)
    ):
        raise ValidationError(
            "Evidence or assessment changed. Reload and review the current facts before saving."
        )
    chosen = next((link for key, _, link in scenarios(issue) if key == values["scenario"]), None)
    if chosen is None:
        raise ValidationError("Select an active linked scenario")
    if issue.finding_id:
        stale = any(link_state(chosen).values())
    else:
        stale = (
            chosen.issue_revision.snapshot != data_for(issue)
            or not chosen.risk_revision.risk.source.enabled
            or chosen.risk_revision.risk.missing_since is not None
            or chosen.risk_revision.risk.current_revision_id != chosen.risk_revision_id
        )
    if stale:
        raise ValidationError("The selected scenario/evidence changed; review and renew its mapping first")
    if values["decision"] == "accept":
        require(actor.is_superuser or role_for(actor, issue.organization) == "admin")
    current = evidence(issue)
    snapshot = {
        name: (value.pk if name == "owner" else value.isoformat() if hasattr(value, "isoformat") else value)
        for name, value in values.items()
        if name not in {"previous_revision", "reviewed_evidence"}
    }
    score = values["likelihood"] * values["impact"]
    residual = values["residual_likelihood"] * values["residual_impact"]
    pinned_issue = issue_snapshot(issue, actor)
    snapshot.update(
        method="bearings-local-5x5/v1",
        score=score,
        band=band(score),
        residual_score=residual,
        residual_band=band(residual),
        owner_name=values["owner"].name,
        evidence=current,
        issue_revision=pinned_issue.pk,
        risk_revision=chosen.risk_revision_id,
        accepted_by=actor.pk if values["decision"] == "accept" else None,
    )
    if issue.finding_id:
        snapshot["cve_revision"] = snapshot_evidence(issue.finding.record).pk
    revision = BusinessRiskRevision.objects.create(
        issue=issue, actor=actor, snapshot=snapshot, evidence_hash=digest(current), previous=latest
    )
    audit(
        actor,
        issue.organization,
        "risk.business_assessed",
        revision.pk,
        issue=str(issue.pk),
        decision=values["decision"],
        method=snapshot["method"],
    )
    return revision
