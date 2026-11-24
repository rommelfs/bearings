"""Scoped, live host summaries. Unknown evidence never becomes a healthy/update claim."""

from datetime import timedelta
from django.core.paginator import Paginator
from django.db.models import (
    Prefetch,
    Case,
    Count,
    F,
    Func,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
    BooleanField,
    DateTimeField,
    DurationField,
    ExpressionWrapper,
)
from django.db.models.functions import Cast, Coalesce, Now
from django.utils import timezone
from .circl import findings_for
from .issues import ACTIVE, visible_issues
from .models import AgentDevice, Installation
from .review_focus import posture
from .review_queue import classified
from .table_sort import TableSort
from .inventory_presentation import additional_software_filter


class HasVendorFix(Func):
    """Same explicit fixed-note/strict satisfied-bound contract as update_context.

    Evaluate in the database before counts, filtering and pagination; never fetch
    every retained proof or infer an installable repository candidate.
    """

    arity = 1
    output_field = BooleanField()

    def as_postgresql(self, compiler, connection, **extra):
        source, params = compiler.compile(self.source_expressions[0])

        def array(path):
            return f"CASE WHEN jsonb_typeof({source} #> '{{package_check,{path}}}') = 'array' THEN {source} #> '{{package_check,{path}}}' ELSE '[]'::jsonb END"

        sql = f"""EXISTS(SELECT 1 FROM jsonb_array_elements({array("comparisons")}) hc(value),
            jsonb_array_elements({array("vendor_comments")}) hn(value)
            WHERE jsonb_typeof(hc.value->'vendor_version')='string'
            AND hc.value->>'vendor_version' <> ''
            AND hc.value->>'operation'='less than' AND hc.value->'matches'='true'::jsonb
            AND jsonb_typeof(hn.value)='string'
            AND strpos(hn.value #>> '{{}}', %s || (hc.value->>'vendor_version') || %s)>0)"""
        return sql, [*params, *params, *params, *params, "has been fixed (note: '", "')"]

    def as_sqlite(self, compiler, connection, **extra):
        source, params = compiler.compile(self.source_expressions[0])

        def array(path):
            return f"CASE WHEN json_type({source}, '$.package_check.{path}')='array' THEN json_extract({source}, '$.package_check.{path}') ELSE '[]' END"

        comparison = "CASE WHEN hc.type='object' THEN hc.value ELSE '{}' END"
        sql = f"""EXISTS(SELECT 1 FROM json_each({array("comparisons")}) hc,
            json_each({array("vendor_comments")}) hn
            WHERE json_type({comparison}, '$.vendor_version')='text'
            AND json_extract({comparison}, '$.vendor_version') <> ''
            AND json_extract({comparison}, '$.operation')='less than'
            AND json_type({comparison}, '$.matches')='true' AND hn.type='text'
            AND instr(hn.value, %s || json_extract({comparison}, '$.vendor_version') || %s)>0)"""
        return sql, [*params, *params, *params, *params, "has been fixed (note: '", "')"]


def count_for(queryset, field, grouping):
    grouped = (
        queryset.order_by().values(grouping).annotate(total=Count(field, distinct=True)).values("total")[:1]
    )
    return Coalesce(Subquery(grouped, output_field=IntegerField()), Value(0))


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
    machine_scope = posture(request.user, [org.pk], include_totals=False)["machines"]
    reviews = classified(findings_for(request.user).filter(organization=org)).filter(
        installation__asset_id=OuterRef("pk")
    )
    automatic = reviews.filter(package_current=True, distro_match__queue_proof__verdict="affected")
    fixes = automatic.annotate(has_vendor_fix=HasVendorFix(F("distro_match__snapshot"))).filter(
        has_vendor_fix=True
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
        | Q(agent_component__observed_at__lt=timezone.now() - timedelta(hours=12))
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
    machines = machine_scope.annotate(
        affected_packages=Case(
            When(evaluated=True, then=count_for(automatic, "installation_id", "installation__asset_id")),
            default=Value(0),
        ),
        fix_packages=Case(
            When(evaluated=True, then=count_for(fixes, "installation_id", "installation__asset_id")),
            default=Value(None),
            output_field=IntegerField(),
        ),
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
        unresolved_packages=Case(
            When(
                evaluated=True,
                then=count_for(
                    reviews.filter(package_current=True, queue_bucket="unresolved"),
                    "installation_id",
                    "installation__asset_id",
                ),
            ),
            default=Value(0),
        ),
        mapping_gaps=count_for(unmapped.filter(asset_id=OuterRef("pk")), "pk", "asset_id"),
        issue_count=count_for(issues, "pk", "asset_id"),
        issue_priority=Subquery(issue_order, output_field=IntegerField()),
        report_time=Subquery(devices.order_by("-last_observed_at").values("last_observed_at")[:1]),
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
    query = request.GET.get("host_q", "").strip()[:128]
    if query:
        machines = machines.filter(name__icontains=query)
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
        ).only("asset_id", "os", "last_observed_at", "expires_at", "distro_summary")
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
            host.priority_label = (
                "No current version matches"
                if host.evaluated and not host.partial and not host.has_gaps
                else "Assessment incomplete"
                if host.evaluated
                else "Assessment unavailable"
            )
            if host.saved_affected:
                host.priority_label = "Saved affected assessment"
            host.priority_tone = (
                "clear" if host.evaluated and not host.has_gaps and not host.saved_affected else "unknown"
            )
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
        "host_return_url": request.path + sorting.url(return_to=None),
        "host_filter": filter_key,
        **{"host_" + key: value for key, value in sorting.context(page).items()},
    }
