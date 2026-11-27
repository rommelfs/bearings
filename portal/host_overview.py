"""Scoped, live host summaries. Unknown evidence never becomes a healthy/update claim."""

from datetime import timedelta
from django.core.paginator import Paginator
from django.db.models import (
    Prefetch,
    Case,
    Count,
    F,
    IntegerField,
    Min,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
    DateTimeField,
    DurationField,
    ExpressionWrapper,
)
from django.db.models.functions import Cast, Coalesce, Now
from django.utils import timezone
from django.urls import reverse
from .agent_freshness import recent_component
from .circl import findings_for
from .distro_fix_evidence import HasVendorFix
from .issues import ACTIVE, visible_issues
from .models import AgentDevice, Installation
from .review_focus import machine_coverage
from .review_queue import CLEARED_VERDICTS, NO_FIX_EVIDENCE, classified
from .review_work import positive_package_coverage
from .presentation import severity_rank
from .table_sort import TableSort
from .inventory_presentation import additional_software_filter


MAX_GROUPED_PACKAGE_HOSTS = 250


def count_for(queryset, field, grouping):
    grouped = (
        queryset.order_by().values(grouping).annotate(total=Count(field, distinct=True)).values("total")[:1]
    )
    return Coalesce(Subquery(grouped, output_field=IntegerField()), Value(0))


def _correlated_package_counts(reviews):
    reviews = classified(reviews).filter(package_current=True)
    automatic = reviews.filter(distro_match__queue_proof__verdict="affected")
    fixes = automatic.annotate(has_vendor_fix=HasVendorFix(F("distro_match__vendor_fix_inputs"))).filter(
        has_vendor_fix=True
    )
    priority = (
        automatic.annotate(rank=severity_rank("record__source_severity")).order_by("rank").values("rank")[:1]
    )
    return {
        "source_priority": Case(
            When(evaluated=True, then=Subquery(priority)),
            default=Cast(Value(None), IntegerField()),
        ),
        "affected_packages": Case(
            When(evaluated=True, then=count_for(automatic, "installation_id", "installation__asset_id")),
            default=Value(0),
        ),
        "fix_packages": Case(
            When(evaluated=True, then=count_for(fixes, "installation_id", "installation__asset_id")),
            default=Value(None),
            output_field=IntegerField(),
        ),
        "unresolved_packages": Case(
            When(
                evaluated=True,
                then=count_for(
                    reviews.filter(queue_bucket="unresolved"), "installation_id", "installation__asset_id"
                ),
            ),
            default=Value(0),
        ),
    }


def _package_counts(reviews, hosts):
    """Summarize current proofs once for a bounded organization host cohort."""
    affected = Q(distro_match__queue_proof__verdict="affected")
    # Currentness is proven by the outer filter. The unresolved bucket therefore
    # needs only the verdict and saved-assessment predicates here.
    unresolved = (
        ~affected
        & ~Q(distro_match__queue_proof__verdict__in=CLEARED_VERDICTS)
        & ~NO_FIX_EVIDENCE
        & ~Q(analyst_applicability__in=("affected", "not_affected"))
    )
    counts = (
        classified(reviews, assets=hosts.order_by().values("pk"))
        .filter(package_current=True)
        .alias(has_vendor_fix=HasVendorFix(F("distro_match__vendor_fix_inputs")))
        .order_by()
        .values("installation__asset_id")
        .annotate(
            affected_packages=Count("installation_id", distinct=True, filter=affected),
            fix_packages=Count("installation_id", distinct=True, filter=affected & Q(has_vendor_fix=True)),
            unresolved_packages=Count("installation_id", distinct=True, filter=unresolved),
            source_priority=Min(severity_rank("record__source_severity"), filter=affected),
        )[: MAX_GROUPED_PACKAGE_HOSTS + 1]
    )
    rows = list(counts)
    if len(rows) > MAX_GROUPED_PACKAGE_HOSTS:
        return _correlated_package_counts(reviews.filter(installation__asset_id=OuterRef("pk")))

    annotations = {}
    for field in ("affected_packages", "fix_packages", "unresolved_packages", "source_priority"):
        default = None if field in {"fix_packages", "source_priority"} else 0
        by_value = {}
        for row in rows:
            value = row[field]
            if value is not None and (value or field == "source_priority"):
                by_value.setdefault(value, []).append(row["installation__asset_id"])
        cases = [When(evaluated=True, pk__in=ids, then=Value(value)) for value, ids in by_value.items()]
        if field == "fix_packages":
            cases.append(When(evaluated=True, then=Value(0)))
        annotations[field] = Case(
            *cases, default=Cast(Value(default), IntegerField()), output_field=IntegerField()
        )
    return annotations


def overview(request, org):
    filter_key = request.GET.get("host_filter", "all")
    filters = {
        "all": Q(),
        "attention": Q(has_problems=True),
        "affected": Q(affected_packages__gt=0),
        "gaps": Q(has_gaps=True),
        "fixes": Q(fix_packages__gt=0),
        "unknown": Q(evaluated=False),
    }
    if filter_key not in filters:
        raise ValueError("Unsupported host filter")
    sorting = TableSort(
        request,
        [
            ("host", "Host", "name", False),
            ("priority", "Problems / highest priority", "host_priority", True),
            ("coverage", "CVE evaluation / gaps", "coverage_order", False),
            ("fixes", "Vendor fixes", "fix_packages", False),
            ("observed", "Last report", "report_time", False),
        ],
    )
    machines, evaluation_available = machine_coverage(request.user, [org.pk])
    query = request.GET.get("host_q", "").strip()[:128]
    if query:
        machines = machines.filter(name__icontains=query)
    scoped_reviews = findings_for(request.user).filter(organization=org)
    reviews = scoped_reviews.filter(installation__asset_id=OuterRef("pk"))
    package_counts = (
        _package_counts(scoped_reviews, machines)
        if evaluation_available
        else {
            "source_priority": Cast(Value(None), IntegerField()),
            "affected_packages": Value(0),
            "fix_packages": Value(None, output_field=IntegerField()),
            "unresolved_packages": Value(0),
        }
    )
    issues = visible_issues(request.user, standalone=True).filter(
        organization=org, asset_id=OuterRef("pk"), status__in=ACTIVE
    )
    devices = AgentDevice.objects.filter(
        organization=org, asset_id=OuterRef("pk"), source_id=OuterRef("source_id"), enabled=True
    )
    applications = Installation.objects.filter(product__organization=org).filter(additional_software_filter())
    unmapped = applications.filter(
        Q(product__watch__isnull=True)
        | Q(product__watch__enabled=False)
        | Q(product__watch__vendor="")
        | Q(product__watch__product_key="")
        | Q(product__watch__requested=True)
        | Q(product__watch__last_success__isnull=True)
        | ~Q(product__watch__error="")
        | Q(
            product__watch__last_success__lt=ExpressionWrapper(
                Now()
                - ExpressionWrapper(
                    Cast(F("product__watch__interval_minutes"), IntegerField()) * Value(timedelta(minutes=2)),
                    output_field=DurationField(),
                ),
                output_field=DateTimeField(),
            )
        )
        | Q(version="")
        | Q(agent_component__missing_since__isnull=False)
        | (Q(agent_component__isnull=False) & ~recent_component("agent_component__"))
    )
    issue_order = (
        issues.annotate(
            rank=Case(
                When(priority="critical", then=Value(0)),
                When(priority="high", then=Value(1)),
                When(priority="low", then=Value(3)),
                default=Value(6),
            )
        )
        .order_by("rank")
        .values("rank")[:1]
    )
    machines = machines.annotate(
        **package_counts,
        manual_packages=count_for(
            reviews.filter(distro_match__isnull=True, status__in=ACTIVE).exclude(
                analyst_applicability="not_affected"
            ),
            "installation_id",
            "installation__asset_id",
        ),
        saved_affected=count_for(
            reviews.filter(analyst_applicability="affected", status__in=[*ACTIVE, "accepted_risk"]),
            "installation_id",
            "installation__asset_id",
        ),
        mapping_gaps=count_for(unmapped.filter(asset_id=OuterRef("pk")), "pk", "asset_id"),
        issue_count=count_for(issues, "pk", "asset_id"),
        issue_priority=Subquery(issue_order, output_field=IntegerField()),
        report_time=Subquery(
            devices.annotate(fresh_at=Coalesce("inventory_verified_at", "last_observed_at"))
            .order_by("-fresh_at")
            .values("fresh_at")[:1]
        ),
    ).annotate(
        host_priority=Case(
            When(source_priority__isnull=True, then=F("issue_priority")),
            When(issue_priority__lt=F("source_priority"), then=F("issue_priority")),
            default=F("source_priority"),
            output_field=IntegerField(),
        ),
        has_gaps=Case(
            When(
                Q(evaluated=False)
                | Q(missing_since__isnull=False)
                | Q(partial=True)
                | Q(mapping_gaps__gt=0)
                | Q(manual_packages__gt=0)
                | Q(unresolved_packages__gt=0),
                then=Value(True),
            ),
            default=Value(False),
        ),
        has_problems=Case(
            When(
                Q(affected_packages__gt=0)
                | Q(missing_since__isnull=False)
                | Q(issue_count__gt=0)
                | Q(manual_packages__gt=0)
                | Q(saved_affected__gt=0),
                then=Value(True),
            ),
            default=Value(False),
        ),
    )
    stats = machines.order_by().aggregate(
        total=Count("pk"),
        problems=Count("pk", filter=Q(has_problems=True)),
        gaps=Count("pk", filter=Q(has_gaps=True)),
        fixes=Count("pk", filter=Q(fix_packages__gt=0)),
        affected=Count("pk", filter=Q(affected_packages__gt=0)),
        unknown=Count("pk", filter=Q(evaluated=False)),
    )
    scope = machines.filter(filters[filter_key]).annotate(
        coverage_order=Case(
            When(evaluated=False, then=Value(2)),
            When(has_gaps=True, then=Value(1)),
            default=Value(0),
        )
    )
    # Only page-sized scalar asset fields are hydrated. Proofs stay in SQL.
    paginator = Paginator(
        scope.select_related("organization", "source__instance")
        .prefetch_related(
            Prefetch(
                "installations",
                queryset=unmapped.select_related("product")
                .only("asset_id", "version", "product__name")
                .order_by("product__name", "pk")[:3],
                to_attr="host_gap_applications",
            ),
            Prefetch(
                "installations",
                queryset=Installation.objects.filter(product__organization=org, is_operating_system=True)
                .select_related("product")
                .only("asset_id", "version", "product__name")
                .order_by("pk")[:1],
                to_attr="host_os_installation",
            ),
        )
        .defer("upstream_data")
        .order_by(sorting.order, "name", "pk"),
        25,
    )
    paginator.count = stats[{"all": "total", "attention": "problems"}.get(filter_key, filter_key)]
    page = paginator.get_page(request.GET.get("page"))
    page.object_list = list(page.object_list)
    device_map = {
        device.asset_id: device
        for device in AgentDevice.objects.filter(
            organization=org,
            asset_id__in=[host.pk for host in page],
            source_id=F("asset__source_id"),
            enabled=True,
        ).only("asset_id", "os", "last_observed_at", "inventory_verified_at", "expires_at", "distro_summary")
    }
    for host in page:
        device = device_map.get(host.pk)
        host.host_device = device
        os = device.os if device and isinstance(device.os, dict) else {}
        os_name = {
            "ubuntu": "Ubuntu",
            "debian": "Debian",
            "rhel": "Red Hat Enterprise Linux",
            "windows": "Windows",
            "rocky": "Rocky Linux",
            "almalinux": "AlmaLinux",
            "centos": "CentOS",
        }.get(os.get("id"), os.get("id", ""))
        host.host_os = " ".join(str(value) for value in (os_name, os.get("version", "")) if value)
        if not host.host_os and host.host_os_installation:
            installed = host.host_os_installation[0]
            host.host_os = " ".join(filter(None, (installed.product.name, installed.version)))
        host.host_report_stale = bool(device and (device.stale or device.expires_at <= timezone.now()))
        summary = device.distro_summary if device and isinstance(device.distro_summary, dict) else {}
        packages = summary.get("packages")
        host.evaluation_packages = (
            packages if host.evaluated and type(packages) is int and packages >= 0 else None
        )
        if host.host_priority is not None:
            host.priority_label = {
                0: "Critical",
                1: "High",
                2: "Medium",
                3: "Low",
                4: "None",
                5: "Unknown",
                6: "Review needed",
            }.get(host.host_priority, "Unknown")
            host.priority_tone = {0: "critical", 1: "high", 2: "medium", 3: "low"}.get(
                host.host_priority, "unknown"
            )
            host.priority_origin = (
                "asset issue"
                if host.issue_priority is not None
                and host.host_priority == host.issue_priority
                and (host.source_priority is None or host.issue_priority < host.source_priority)
                else "source"
            )
        else:
            clear = (
                not host.has_problems
                and not host.has_gaps
                and positive_package_coverage(summary, host.evaluated and not host.partial)
            )
            host.priority_label = (
                "✓ No open vulnerabilities in checked scope"
                if clear
                else "Assessment incomplete"
                if host.evaluated
                else "Assessment unavailable"
            )
            if host.saved_affected:
                host.priority_label = "Saved affected assessment"
            host.priority_tone = "clear" if clear else "unknown"
            host.priority_origin = ""
    metric_definitions = [
        ("all", "total", "Active hosts"),
        ("attention", "problems", "With problems / reviews"),
        ("gaps", "gaps", "With evaluation gaps"),
        ("fixes", "fixes", "With documented vendor fixes"),
    ]
    metrics = [
        {
            "label": label,
            "count": stats[key],
            "key": value,
            "active": value == filter_key,
            "url": sorting.url(host_filter=value, page=None) + "#hosts",
        }
        for value, key, label in metric_definitions
    ]
    return {
        "host_page": page,
        "host_stats": stats,
        "host_metrics": metrics,
        "host_query": query,
        "host_return_url": reverse("organization", args=[org.slug]) + sorting.url(return_to=None),
        "host_filter": filter_key,
        **{"host_" + key: value for key, value in sorting.context(page).items()},
    }
