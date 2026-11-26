from time import perf_counter
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction, OperationalError
from django.db.models import Case, When, Value, IntegerField, Count, Min, F, Q, CharField
from django.db.models.functions import Coalesce, Cast
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods
from . import inventory_csv, issues
from .access import (
    analyst_read_snapshot,
    audit,
    can_review_contact,
    organizations_for,
    require,
    is_analyst,
    organization,
    visible_findings_for,
)
from .circl_views import private_response
from .models import InventoryCSVBatch, InventorySource, InfrastructureClaim, AssetIssue
from .overview_queries import overview_queries, read_snapshot
from .scope import normalize
from .queue_context import with_return
from .review_work import without_cleared_issue_shells
from django.urls import reverse


class StartForm(forms.Form):
    scope = forms.CharField(max_length=255, label="One domain, static IP, network or IP range")
    network_context = forms.CharField(
        max_length=100, required=False, label="Internal network context (for private addresses)"
    )

    def clean_scope(self):
        value = self.cleaned_data["scope"].strip()

        for kind in ["ip", "network", "range", "domain"]:
            try:
                return kind, normalize(kind, value)
            except ValidationError:
                continue
        raise forms.ValidationError(
            "Enter a domain without URL/wildcard, IP, CIDR network or start-end range"
        )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def start(request, slug):
    org = organization(request, slug)
    require(can_review_contact(request.user, org))
    form = StartForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        from .configuration import locked_owner

        with transaction.atomic():
            org = locked_owner(request.user, org)
            kind, value = form.cleaned_data["scope"]
            current = InfrastructureClaim.objects.filter(
                organization=org,
                kind=kind,
                value=value,
                network_context=form.cleaned_data["network_context"],
                status__in=["declared", "verified"],
                valid_from__lte=timezone.now(),
            ).filter(Q(valid_until=None) | Q(valid_until__gt=timezone.now()))
            if not current.exists():
                claim = InfrastructureClaim(
                    organization=org,
                    kind=kind,
                    value=value,
                    network_context=form.cleaned_data["network_context"],
                )
                claim.full_clean()
                claim.save()
                audit(request.user, org, "scope.created", claim.pk)
        messages.success(
            request,
            "Scope saved as your declaration. Add inventory whenever you are ready; responsibility verification remains separate.",
        )
        return redirect("overview")
    return private_response(
        render(
            request,
            "portal/company_start.html",
            {"org": org, "form": form, "contacts": org.contacts.order_by("pk")[:5]},
        )
    )


class UploadForm(forms.Form):
    file = forms.FileField(label="Inventory CSV (UTF-8, comma or semicolon, max 1 MB / 500 rows)")


@login_required
@never_cache
@sensitive_post_parameters()
@require_http_methods(["GET", "POST"])
def csv_upload(request, slug):
    org = organization(request, slug)
    source = get_object_or_404(InventorySource, organization=org)
    inventory_csv.authorize(request.user, org, source)
    form = UploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            batch = inventory_csv.preview(request.user, org, form.cleaned_data["file"].read(1_000_001))
        except ValidationError as error:
            form.add_error(None, error)
        else:
            return redirect("csv-preview", slug=slug, pk=batch.pk)
    return private_response(render(request, "portal/csv_upload.html", {"org": org, "form": form}))


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def csv_preview(request, slug, pk):
    org = organization(request, slug)
    source = get_object_or_404(InventorySource, organization=org)
    inventory_csv.authorize(request.user, org, source)
    batch = get_object_or_404(InventoryCSVBatch, pk=pk, organization=org, source=source, actor=request.user)
    error = None
    status = 200
    if batch.expires_at <= timezone.now() and batch.status != "committed":
        return private_response(
            render(request, "portal/csv_preview.html", {"org": org, "expired": True}, status=410)
        )
    if request.method == "POST":
        require(request.POST.get("confirmed") == "on")
        try:
            batch = inventory_csv.commit(request.user, org, batch.pk)
        except ValidationError as failure:
            error = failure.messages
            status = 409
        else:
            return redirect("csv-preview", slug=slug, pk=pk)
    return private_response(
        render(
            request, "portal/csv_preview.html", {"org": org, "batch": batch, "error": error}, status=status
        )
    )


@login_required
@require_http_methods(["GET"])
def csv_template(request, slug):
    org = organization(request, slug)
    inventory_csv.authorize(request.user, org, get_object_or_404(InventorySource, organization=org))
    response = HttpResponse(
        "asset_key,name,kind,ip,domain,software,version,software_key\nserver-001,Example server,server,192.0.2.10,server.example.invalid,Apache Log4j,2.14.1,log4j\n",
        content_type="text/csv; charset=utf-8",
    )
    response["Content-Disposition"] = 'attachment; filename="bearings-inventory-template.csv"'
    return private_response(response)


@login_required
@never_cache
@analyst_read_snapshot
@require_http_methods(["GET"])
def actions(request):
    started = perf_counter()
    operator = request.user.is_superuser or is_analyst(request.user)
    if operator:
        audit(request.user, None, "operator.company_actions")
    orgs = organizations_for(request.user)
    selected = request.GET.get("organization", "")
    if selected:
        orgs = orgs.filter(pk=get_object_or_404(orgs, slug=selected).pk)
    mode = request.GET.get("view", "machines")
    if mode not in {"machines", "groups"}:
        return HttpResponse("Unsupported attention view", status=400)
    if mode == "machines":
        from .attention_machines import page_for

        try:
            with (
                read_snapshot(),
                overview_queries(query_timeout_ms=5000, budget_ms=12000, planning_limit=4) as database,
            ):
                page = page_for(
                    request.user,
                    orgs.values_list("pk", flat=True),
                    request.GET.get("page"),
                    scoped_evidence=bool(selected) or not operator,
                )
                render_started = perf_counter()
                response = private_response(
                    render(request, "portal/attention_machines.html", {"page": page, "selected": selected})
                )
                render_ms = (perf_counter() - render_started) * 1000
            response["Server-Timing"] = (
                f"actions;dur={(perf_counter() - started) * 1000:.1f}, "
                f"database;dur={database.seconds * 1000:.1f}, "
                f"dbmax;dur={database.slowest * 1000:.1f}, "
                f"render;dur={render_ms:.1f}"
            )
            return response
        except OperationalError:
            return private_response(
                render(
                    request,
                    "portal/attention_machines.html",
                    {"unavailable": True, "selected": selected},
                    status=503,
                )
            )
    base = (
        issues.visible_issues(request.user)
        .filter(issues.active_filter(), asset__lifecycle="active")
        .exclude(finding__analyst_applicability="not_affected")
    )
    if selected:
        base = base.filter(organization__in=orgs)
    base = without_cleared_issue_shells(base, visible_findings_for(request.user))
    try:
        with overview_queries(query_timeout_ms=3000, budget_ms=8000, planning_limit=4):
            severity = Case(
                When(Q(priority="critical") | Q(finding__record__source_severity="critical"), then=Value(0)),
                When(Q(priority="high") | Q(finding__record__source_severity="high"), then=Value(1)),
                When(priority="review", then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            )
            base = base.annotate(
                action_title=Case(
                    When(finding__isnull=False, then=F("installation__product__name")), default=F("title")
                ),
                effective_priority=severity,
            )
            base = base.annotate(target_deadline=Coalesce("action_due", "event_date"))
            groups = (
                base.values(
                    "organization__slug",
                    "organization__name",
                    "kind",
                    "installation__product_id",
                    "action_title",
                )
                .annotate(
                    representative=Min(Cast("pk", output_field=CharField())),
                    count=Count("pk"),
                    assets=Count("asset_id", distinct=True),
                    priority=Min("effective_priority"),
                    due=Min("target_deadline"),
                    overdue=Count("pk", filter=Q(target_deadline__lt=timezone.localdate())),
                    unassigned=Count("pk", filter=Q(owner_team="")),
                    uncertain=Count(
                        "pk", filter=Q(finding__analyst_applicability__in=["unknown", "unassessed"])
                    ),
                )
                .order_by(
                    "priority",
                    "-overdue",
                    F("due").asc(nulls_last=True),
                    "organization__name",
                    "action_title",
                    "installation__product_id",
                )
            )
            page = Paginator(groups, 20).get_page(request.GET.get("page"))
            page.object_list = list(page.object_list)
    except OperationalError:
        return private_response(
            render(request, "portal/company_actions.html", {"unavailable": True}, status=503)
        )
    return private_response(
        render(request, "portal/company_actions.html", {"page": page, "selected": selected})
    )


class ActionForm(forms.Form):
    operation = forms.ChoiceField(
        choices=[
            ("assign", "Assign / schedule"),
            ("acknowledge", "Acknowledge and start review"),
            ("evidence", "Record remediation evidence"),
        ]
    )
    owner_team = forms.CharField(max_length=180, required=False, label="Responsible person / team")
    action_due = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    note = forms.CharField(
        max_length=4000, widget=forms.Textarea(attrs={"rows": 3}), label="Note / remediation evidence"
    )
    token = forms.CharField(widget=forms.HiddenInput)


def action_state(issue):
    return inventory_csv.digest(
        {
            "facts": issues.data_for(issue),
            "status": issue.current_status,
            "updated": issue.updated_at.isoformat(),
        }
    )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def act(request, slug, pk):
    org = organization(request, slug)
    issue = get_object_or_404(issues.visible_issues(request.user), organization=org, pk=pk)
    require(issues.editable(request.user, issue))
    form = ActionForm(
        request.POST if request.method == "POST" else None,
        initial={
            "owner_team": issue.owner_team,
            "action_due": issue.action_due,
            "token": signing.dumps(
                {"issue": str(pk), "actor": request.user.pk, "state": action_state(issue)},
                salt="company-action",
            ),
        },
    )
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                issue = AssetIssue.objects.select_for_update().get(pk=pk)
                require(
                    issues.visible_issues(request.user).filter(pk=pk).exists()
                    and issues.editable(request.user, issue)
                )
                proof = signing.loads(form.cleaned_data["token"], salt="company-action", max_age=3600)
                if proof != {"issue": str(pk), "actor": request.user.pk, "state": action_state(issue)}:
                    raise ValidationError("The issue changed. Reload and review the current state.")
                values = {
                    "owner_team": form.cleaned_data["owner_team"],
                    "action_due": form.cleaned_data["action_due"],
                }
                if form.cleaned_data["operation"] == "acknowledge" and issue.current_status == "new":
                    if issue.finding_id:
                        from .services import transition_finding

                        transition_finding(
                            request.user, issue.finding, "under_review", form.cleaned_data["note"]
                        )
                    else:
                        values["status"] = "under_review"
                issues.save_issue(request.user, issue, values, form.cleaned_data["note"])
            messages.success(
                request,
                "Action recorded. Remediation evidence does not automatically resolve a finding or prove a patch is installed.",
            )
            return redirect(with_return(request, reverse("issue", args=[slug, pk])))
        except (ValidationError, signing.BadSignature) as error:
            form.add_error(
                None, error.messages if isinstance(error, ValidationError) else "Action form expired; reload"
            )
    return private_response(
        render(request, "portal/company_action.html", {"org": org, "issue": issue, "form": form})
    )
