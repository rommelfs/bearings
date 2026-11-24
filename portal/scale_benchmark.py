"""Synthetic data and bounded profiling for a separately owned PostgreSQL scale lab."""

import json
import os
from pathlib import Path
from time import perf_counter
from datetime import timedelta
from collections import defaultdict
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.utils import timezone
from . import models as m
from .access import ANALYST_GROUP

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".local/scale-test"


def guard():
    if (
        os.getenv("BEARINGS_SCALE_TEST") != "1"
        or connection.vendor != "postgresql"
        or not connection.settings_dict["NAME"].startswith("bearings_scale_")
        or os.environ.get("DJANGO_SETTINGS_MODULE") != "scripts.scale_settings"
    ):
        raise CommandError("Refusing anything except explicitly isolated PostgreSQL scale settings/database")


def bulk(model, objects):
    return model.objects.bulk_create(objects, batch_size=2000)


def seed(companies, assets_per_company):
    if not 1 <= companies <= 100000 or not 10 <= assets_per_company <= 100:
        raise CommandError("Use 1–100000 companies and 10–100 assets per company")
    with connection.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS bearings_scale_manifest (id integer PRIMARY KEY CHECK(id=1), data jsonb NOT NULL)"
        )
        cursor.execute("SELECT data FROM bearings_scale_manifest WHERE id=1")
        existing = cursor.fetchone()
    if existing:
        raise CommandError("Scale database already has a manifest; use measure (no destructive reseed)")
    if m.Organization.objects.exists() or get_user_model().objects.exists():
        raise CommandError("Scale seed requires an empty database, with no pre-existing organizations/users")
    started = perf_counter()
    actor = get_user_model().objects.create(
        username="scale-analyst", password="!scale-unusable", is_active=True
    )
    actor.groups.add(Group.objects.get_or_create(name=ANALYST_GROUP)[0])
    now, today = timezone.now(), timezone.localdate()
    specs = [
        (
            "Apache Log4j",
            "pkg:maven/org.apache.logging.log4j/log4j-core",
            "apache",
            "log4j",
            "CVE-2021-44228",
            "critical",
        ),
        (
            "Fortinet FortiOS",
            "cpe:2.3:o:fortinet:fortios:*:*:*:*:*:*:*:*",
            "fortinet",
            "fortios",
            "CVE-2024-21762",
            "high",
        ),
        ("OpenSSL", "pkg:generic/openssl", "openssl", "openssl", "CVE-2022-3602", "high"),
    ]
    counts = defaultdict(int)
    for offset in range(0, companies, 500):
        stop = min(offset + 500, companies)
        with transaction.atomic():
            orgs = bulk(
                m.Organization,
                [
                    m.Organization(
                        name=f"SYNTHETIC Scale Company {i:05d}",
                        slug=f"scale-{i:05d}",
                        postal_address=f"{1 + i % 80}, rue SYNTHETIC\nL-2449 Luxembourg\nLuxembourg"
                        if i % 7
                        else "",
                        operator_visibility=i % 10 != 0,
                    )
                    for i in range(offset, stop)
                ],
            )
            users = bulk(
                get_user_model(),
                [
                    get_user_model()(
                        username=f"scale-owner-{i:05d}",
                        password="!scale-unusable",
                        email=f"owner@company-{i:05d}.example.invalid",
                    )
                    for i in range(offset, stop)
                ],
            )
            bulk(
                m.Membership,
                [m.Membership(organization=o, user=u, role="admin") for o, u in zip(orgs, users)],
            )
            contacts = bulk(
                m.Contact,
                [
                    m.Contact(
                        organization=o,
                        name="SYNTHETIC Security Team",
                        email=f"security@{o.slug}.example.invalid",
                        notification_enabled=True,
                        reviewed_at=now,
                        reachable_at=now if i % 5 else None,
                        next_review=today + timedelta(days=90),
                    )
                    for i, o in enumerate(orgs, offset)
                ],
            )
            bulk(
                m.Contact,
                [
                    m.Contact(
                        organization=o,
                        name="SYNTHETIC Escalation Team",
                        function="management",
                        email=f"noc@{o.slug}.example.invalid",
                        next_review=today + timedelta(days=90),
                    )
                    for o in orgs
                ],
            )
            sources = bulk(
                m.InventorySource,
                [m.InventorySource(organization=o, mode="manual", import_enabled=False) for o in orgs],
            )
            bulk(
                m.InventoryReviewPolicy,
                [
                    m.InventoryReviewPolicy(
                        organization=o,
                        email_enabled=True,
                        next_due=today - timedelta(days=i % 30),
                        last_reviewed_at=now - timedelta(days=100),
                    )
                    for i, o in enumerate(orgs, offset)
                ],
            )
            bulk(
                m.InfrastructureClaim,
                [
                    m.InfrastructureClaim(organization=o, kind="domain", value=f"{o.slug}.example.invalid")
                    for o in orgs
                ],
            )
            bulk(
                m.InfrastructureClaim,
                [
                    m.InfrastructureClaim(
                        organization=o,
                        kind="network",
                        value=f"10.{i // 256 % 256}.{i % 256}.0/24",
                        network_context="synthetic-private",
                    )
                    for i, o in enumerate(orgs, offset)
                ],
            )
            products = bulk(
                m.Product,
                [m.Product(organization=o, name=s[0], identifier=s[1]) for o in orgs for s in specs],
            )
            watches = bulk(
                m.ProductWatch,
                [
                    m.ProductWatch(
                        product=p,
                        vendor=specs[j % 3][2],
                        product_key=specs[j % 3][3],
                        source_url="https://vulnerability.circl.lu",
                        enabled=False,
                        requested=False,
                        last_success=now,
                    )
                    for j, p in enumerate(products)
                ],
            )
            records = bulk(
                m.SourceRecord,
                [
                    m.SourceRecord(
                        organization=o,
                        source="synthetic-scale-fixture",
                        external_id=s[4],
                        source_severity=s[5],
                        shareable=k != 2,
                        payload={
                            "synthetic": True,
                            "cveMetadata": {"cveId": s[4]},
                            "containers": {
                                "cna": {
                                    "title": "SYNTHETIC scale evidence",
                                    "metrics": [
                                        {
                                            "cvssV3_1": {
                                                "baseScore": 10.0 if k == 0 else 8.1,
                                                "baseSeverity": s[5].upper(),
                                            }
                                        }
                                    ],
                                }
                            },
                        },
                    )
                    for o in orgs
                    for k, s in enumerate(specs)
                ],
            )
            revisions = bulk(
                m.SourceRecordRevision,
                [m.SourceRecordRevision(record=r, content_hash="0" * 64, payload=r.payload) for r in records],
            )
            assets = bulk(
                m.Asset,
                [
                    m.Asset(
                        organization=o,
                        source=s,
                        name=f"{o.slug}-server-{a:02d}",
                        kind="server" if a % 3 else "vm",
                        state="recorded",
                        responsible_contact=c,
                        upstream_data={
                            "synthetic": True,
                            "primary_ip4": {"address": f"10.{i // 256 % 256}.{i % 256}.{a + 1}/32"},
                            "dns_name": f"server-{a:02d}.{o.slug}.example.invalid",
                        },
                    )
                    for i, (o, s, c) in enumerate(zip(orgs, sources, contacts), offset)
                    for a in range(assets_per_company)
                ],
            )
            installations = bulk(
                m.Installation,
                [
                    m.Installation(
                        asset=a,
                        product=products[(j // assets_per_company) * 3 + j % assets_per_company % 3],
                        version=""
                        if j % 10 == 9
                        else ["2.14.1", "7.2.3", "3.0.7"][j % assets_per_company % 3]
                        if j % 4
                        else ["2.17.1", "7.4.3", "3.0.8"][j % assets_per_company % 3],
                    )
                    for j, a in enumerate(assets)
                ],
            )
            vulnerable = [(j, inst) for j, inst in enumerate(installations) if j % assets_per_company < 6]
            findings = bulk(
                m.Finding,
                [
                    m.Finding(
                        organization=orgs[j // assets_per_company],
                        installation=inst,
                        record=records[(j // assets_per_company) * 3 + j % assets_per_company % 3],
                        analyst_applicability="affected" if j % assets_per_company < 2 else "unassessed",
                        status=[
                            "confirmed",
                            "new",
                            "under_review",
                            "accepted_risk",
                            "resolved",
                            "false_positive",
                        ][j % assets_per_company],
                        explanation="SYNTHETIC benchmark evidence",
                    )
                    for j, inst in vulnerable
                ],
            )
            matches = bulk(
                m.DiscoveryMatch,
                [
                    m.DiscoveryMatch(
                        watch=watches[(j // assets_per_company) * 3 + j % assets_per_company % 3],
                        finding=f,
                        evidence_revision=revisions[
                            (j // assets_per_company) * 3 + j % assets_per_company % 3
                        ],
                        input_hash="1" * 64,
                        explanation="SYNTHETIC",
                        result="potential",
                    )
                    for (j, _), f in zip(vulnerable, findings)
                ],
            )
            bulk(
                m.DiscoveryRevision,
                [
                    m.DiscoveryRevision(
                        match=match,
                        fingerprint=str(k) * 64,
                        snapshot={"synthetic": True},
                        created_at=now - timedelta(days=(offset + j) % 29, hours=k),
                    )
                    for j, match in enumerate(matches)
                    for k in (1, 2)
                ],
            )
            bulk(
                m.FindingHistory,
                [
                    m.FindingHistory(
                        finding=f,
                        previous_status="new",
                        status=f.status,
                        reason="SYNTHETIC resolution",
                        created_at=now - timedelta(days=offset % 29),
                    )
                    for f in findings
                    if f.status in {"resolved", "false_positive"}
                ],
            )
            issues = bulk(
                m.AssetIssue,
                [
                    m.AssetIssue(
                        organization=f.organization,
                        asset=f.installation.asset,
                        installation=f.installation,
                        finding=f,
                        kind="vulnerability",
                        title="SYNTHETIC vulnerability review",
                        source_label="Scale fixture",
                        evidence_text="SYNTHETIC",
                        priority="critical" if j % 6 == 0 else "high",
                        action_due=today - timedelta(days=5),
                        status=f.status,
                    )
                    for j, f in enumerate(findings)
                ],
            )
            issues += bulk(
                m.AssetIssue,
                [
                    m.AssetIssue(
                        organization=o,
                        asset=assets[j * assets_per_company + a],
                        kind=kind,
                        title=f"SYNTHETIC {kind} attention",
                        source_label="Scale fixture",
                        evidence_text="SYNTHETIC",
                        priority="high",
                        operator_only=a == 8,
                        action_due=today - timedelta(days=10),
                    )
                    for j, o in enumerate(orgs)
                    for a, kind in [(6, "eol"), (7, "support"), (8, "exposure")]
                ],
            )
            bulk(
                m.IssueRevision,
                [
                    m.IssueRevision(issue=i, digest="2" * 64, snapshot={"synthetic": True, "title": i.title})
                    for i in issues
                ],
            )
            for key, items in [
                ("organizations", orgs),
                ("users", users),
                ("assets", assets),
                ("installations", installations),
                ("products", products),
                ("findings", findings),
                ("issues", issues),
                ("discovery_matches", matches),
            ]:
                counts[key] += len(items)
        print(
            json.dumps(
                {
                    "phase": "seed",
                    "companies": stop,
                    "assets": counts["assets"],
                    "elapsed_s": round(perf_counter() - started, 1),
                }
            ),
            flush=True,
        )
    with connection.cursor() as cursor:
        cursor.execute("ANALYZE")
        manifest = {
            "companies": companies,
            "assets_per_company": assets_per_company,
            "counts": dict(counts),
            "seed_seconds": round(perf_counter() - started, 2),
            "synthetic_only": True,
            "seed_version": 1,
        }
        cursor.execute("INSERT INTO bearings_scale_manifest VALUES(1,%s::jsonb)", [json.dumps(manifest)])
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"phase": "seed_complete", **manifest}), flush=True)


def run(options):
    guard()
    if options["phase"] == "seed":
        seed(options["companies"], options["assets_per_company"])
    elif options["phase"] == "workflows":
        measure_workflows(options)
    else:
        measure(options)


class RequestProfile:
    """Bound the diagnostic itself; a guard abort is a failure, never a successful latency."""

    def __init__(self, seconds=12, queries=1000):
        self.started = perf_counter()
        self.seconds = seconds
        self.maximum = queries
        self.count = 0
        self.sql_ms = 0.0
        self.slowest = []
        self.guard = ""

    def __call__(self, execute, sql, params, many, context):
        from django.db import OperationalError

        if self.count >= self.maximum or perf_counter() - self.started >= self.seconds:
            self.guard = "query_count" if self.count >= self.maximum else "wall_time"
            raise OperationalError("Synthetic scale diagnostic guard exceeded")
        self.count += 1
        started = perf_counter()
        try:
            return execute(sql, params, many, context)
        except OperationalError as error:
            if getattr(error.__cause__, "sqlstate", None) == "57014":
                self.guard = "postgres_timeout"
            raise
        finally:
            elapsed = (perf_counter() - started) * 1000
            self.sql_ms += elapsed
            if sql.lstrip().upper().startswith("SELECT") and '"portal_' in sql:
                self.slowest.append((elapsed, sql, params))
                self.slowest.sort(key=lambda row: row[0], reverse=True)
                del self.slowest[3:]


class ScaleMetricsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        profile = RequestProfile()
        with connection.execute_wrapper(profile):
            response = self.get_response(request)
        response.scale_profile = profile
        response["X-Scale-Queries"] = str(profile.count)
        response["X-Scale-SQL-Ms"] = f"{profile.sql_ms:.1f}"
        response["X-Scale-Guard"] = profile.guard or "none"
        return response


def plans(profile):
    result = []
    for elapsed, sql, params in profile.slowest[:2]:
        try:
            with connection.cursor() as cursor:
                cursor.execute("EXPLAIN (FORMAT JSON) " + sql, params)
                plan = cursor.fetchone()[0]
                if isinstance(plan, str):
                    plan = json.loads(plan)
            result.append({"observed_ms": round(elapsed, 1), "plan": plan})
        except Exception as error:
            result.append({"observed_ms": round(elapsed, 1), "explain_error": type(error).__name__})
    return result


def endpoints(org, asset):
    return [
        ("company_overview", "owner", "get", "/", None),
        ("company_inventory", "owner", "get", "/inventory/", None),
        ("company_detail", "owner", "get", f"/organizations/{org.slug}/", None),
        ("company_asset", "owner", "get", f"/organizations/{org.slug}/assets/{asset.pk}/", None),
        ("company_issues", "owner", "get", "/issues/", None),
        ("company_reviews", "owner", "get", "/reviews/", None),
        ("company_actions", "owner", "get", "/actions/", None),
        ("company_wizard", "owner", "get", f"/organizations/{org.slug}/setup/scope/", None),
        ("national_shell", "analyst", "get", "/circl/", None),
        *[
            ("national_" + panel, "analyst", "get", f"/circl/panels/{panel}/", None)
            for panel in ("summary", "problems", "versions", "activity")
        ],
        ("national_map", "analyst", "get", "/circl/map/data/", None),
        ("national_findings", "analyst", "get", "/circl/findings/", None),
        ("national_company_search", "analyst", "get", "/?q=Scale+Company+123", None),
        ("national_inventory", "analyst", "get", "/inventory/", None),
        ("national_issues", "analyst", "get", "/issues/", None),
        ("national_reviews", "analyst", "get", "/reviews/", None),
        (
            "research_exact",
            "analyst",
            "post",
            "/circl/research/",
            {
                "product": "Apache Log4j",
                "product_match": "exact",
                "mode": "exact",
                "version": "2.14.1",
                "bucket": "matches",
            },
        ),
        (
            "research_range",
            "analyst",
            "post",
            "/circl/research/",
            {
                "product": "Apache Log4j",
                "product_match": "contains",
                "mode": "range",
                "minimum": "2.0.0",
                "maximum": "2.17.0",
                "bucket": "matches",
            },
        ),
    ]


def measure(options):
    import concurrent.futures
    import math
    import platform
    import re
    import statistics
    import resource
    import threading
    import urllib.error
    import urllib.request
    import urllib.parse
    from socketserver import ThreadingMixIn
    from wsgiref.simple_server import WSGIRequestHandler, WSGIServer
    from django.core.management import call_command
    from django.core.wsgi import get_wsgi_application
    from django.test import Client
    from django.test.utils import setup_test_environment
    from django.conf import settings
    from django.db import close_old_connections
    from unittest.mock import patch

    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,50}", options["label"]):
        raise CommandError("Report label must be 1–50 simple filename characters")
    if not 1 <= options["http_repeats"] <= 50:
        raise CommandError("Use 1–50 HTTP repeats per route")
    if not 1 <= options["samples"] <= 10 or not 1 <= options["concurrency"] <= 16:
        raise CommandError("Use 1–10 samples and 1–16 concurrent clients")
    # Refresh planner statistics after new indexes/read-model backfills, before timing requests.
    from .overview_queries import overview_queries

    with overview_queries(query_timeout_ms=30000):
        with connection.cursor() as cursor:
            cursor.execute("ANALYZE")
    with connection.cursor() as cursor:
        cursor.execute("SELECT data FROM bearings_scale_manifest WHERE id=1")
        manifest = cursor.fetchone()[0]
        if isinstance(manifest, str):
            manifest = json.loads(manifest)
        cursor.execute("SELECT version(),pg_database_size(current_database())")
        version, size = cursor.fetchone()
        cursor.execute(
            "SELECT relname,n_live_tup,pg_total_relation_size(relid) FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 15"
        )
        tables = [dict(zip(["table", "estimated_rows", "bytes"], row)) for row in cursor.fetchall()]
    mail_backend = settings.EMAIL_BACKEND
    setup_test_environment()
    settings.EMAIL_BACKEND = mail_backend  # Test template capture must not replace the local file sink.
    org = m.Organization.objects.get(slug="scale-00001" if manifest["companies"] > 1 else "scale-00000")
    asset = org.assets.order_by("name").first()
    owner = get_user_model().objects.get(
        username="scale-owner-00001" if manifest["companies"] > 1 else "scale-owner-00000"
    )
    analyst = get_user_model().objects.get(username="scale-analyst")
    clients = {
        "owner": Client(raise_request_exception=False),
        "analyst": Client(raise_request_exception=False),
    }
    clients["owner"].force_login(owner)
    clients["analyst"].force_login(analyst)
    report = {
        "label": options["label"],
        "dataset": manifest,
        "environment": {
            "postgres": version,
            "database_bytes": size,
            "python": platform.python_version(),
            "host_cpus": os.cpu_count(),
            "debug": False,
            "diagnostic_statement_timeout_ms": 5000,
            "diagnostic_query_limit": 1000,
            "diagnostic_wall_budget_seconds": 12,
            "sso": False,
            "transport": "file only",
            "postgres_cpus": float(os.environ.get("BEARINGS_SCALE_DB_CPUS", "2")),
            "postgres_memory_gib": 3,
        },
        "tables": tables,
        "serial": [],
        "checks": [],
        "workflows": [],
        "http": {},
    }

    def save():
        (OUTPUT / (options["label"] + ".json")).write_text(json.dumps(report, indent=2, default=str) + "\n")

    # No fixture operation may perform a live connector/API/mail request.
    with patch("httpx.Client.send", side_effect=AssertionError("External connectors forbidden in scale lab")):
        for name, role, method, url, data in endpoints(org, asset):
            samples = []
            explain = []
            for sample in range(options["samples"]):
                started = perf_counter()
                response = getattr(clients[role], method)(url, data=data or {})
                elapsed = (perf_counter() - started) * 1000
                profile = response.scale_profile
                row = {
                    "ms": round(elapsed, 1),
                    "status": response.status_code,
                    "queries": profile.count,
                    "sql_ms": round(profile.sql_ms, 1),
                    "guard": profile.guard or None,
                    "bytes": len(response.content),
                    "process_peak_rss_mib": round(
                        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1
                    ),
                    "server_timing": response.get("Server-Timing", ""),
                }
                samples.append(row)
                if sample == 0:
                    explain = plans(profile)
                # Do not repeat known failures; timeouts/guards are not latency successes.
                if response.status_code >= 500:
                    break
            item = {
                "name": name,
                "role": role,
                "samples": samples,
                "median_ms": round(statistics.median(s["ms"] for s in samples), 1),
                "plans": explain,
            }
            report["serial"].append(item)
            save()
            print(
                json.dumps(
                    {
                        "phase": "measure",
                        "name": name,
                        "median_ms": item["median_ms"],
                        "status": samples[-1]["status"],
                        "queries": samples[-1]["queries"],
                        "guard": samples[-1]["guard"],
                    }
                ),
                flush=True,
            )

        def check(name, condition):
            report["checks"].append({"name": name, "passed": bool(condition)})

        check("exact_company_count", m.Organization.objects.count() == manifest["companies"])
        check(
            "exact_asset_count",
            m.Asset.objects.count() == manifest["companies"] * manifest["assets_per_company"],
        )
        check("anonymous_login_required", Client().get("/").status_code == 302)
        check("one_company_per_owner", m.Membership.objects.filter(user=owner).count() == 1)
        check(
            "foreign_asset_denied",
            clients["owner"]
            .get(f"/organizations/{org.slug}/assets/{m.Asset.objects.exclude(organization=org).first().pk}/")
            .status_code
            == 404
            if manifest["companies"] > 1
            else True,
        )
        check("national_denied_to_owner", clients["owner"].get("/circl/").status_code == 403)
        check("national_map_denied_to_owner", clients["owner"].get("/circl/map/data/").status_code == 403)
        check(
            "foreign_company_denied",
            clients["owner"].get("/organizations/scale-00000/").status_code == 404
            if org.slug != "scale-00000"
            else True,
        )
        hidden = m.Organization.objects.filter(operator_visibility=False).exclude(pk=org.pk).first()
        if hidden:
            check(
                "private_company_denied_to_analyst",
                clients["analyst"].get(f"/organizations/{hidden.slug}/").status_code == 404,
            )
        response = clients["analyst"].get("/circl/panels/summary/")
        if response.status_code == 200:
            check(
                "national_scope_company_count",
                response.context["counts"]["organizations"]
                == m.Organization.objects.filter(operator_visibility=True).count(),
            )
            check(
                "national_scope_asset_count",
                response.context["counts"]["inventory_assets"]
                == m.Asset.objects.filter(organization__operator_visibility=True).count(),
            )
        else:
            check("national_summary_available", False)
        inventory = clients["owner"].get(f"/api/v1/organizations/{org.slug}/inventory/")
        inventory_data = inventory.json() if inventory.status_code == 200 else {}
        check(
            "owner_inventory_contains_only_own_assets",
            inventory.status_code == 200
            and inventory_data.get("organization") == org.slug
            and inventory_data.get("pagination", {}).get("count") == manifest["assets_per_company"]
            and all(row["name"].startswith(org.slug + "-") for row in inventory_data.get("assets", [])),
        )
        # Exercise a real scoped write and roll it back, preserving fixture row counts.
        started = perf_counter()
        with transaction.atomic():
            before = org.assets.count()
            response = clients["owner"].post(
                f"/organizations/{org.slug}/assets/new/",
                {
                    "name": "SYNTHETIC benchmark write",
                    "kind": "server",
                    "criticality": "normal",
                    "lifecycle": "active",
                    "responsible_team": "Scale team",
                },
            )
            check("owner_asset_write", response.status_code == 302 and org.assets.count() == before + 1)
            transaction.set_rollback(True)
        report["workflows"].append(
            {"name": "company_asset_write_rolled_back", "ms": round((perf_counter() - started) * 1000, 1)}
        )
        # Real bounded reminder scheduling and local file mail, without exposing link/token bodies.
        import io

        for command, args in [("process_jobs", {}), ("remind_inventory", {"limit": 10})]:
            sent_before = m.InventoryReviewDelivery.objects.filter(status="sent").count()
            messages_before = file_message_count(settings.EMAIL_FILE_PATH)
            started = perf_counter()
            profile = RequestProfile(seconds=20, queries=3000)
            try:
                with connection.execute_wrapper(profile):
                    call_command(command, stdout=io.StringIO(), **args)
                result = "ok"
            except Exception as error:
                result = type(error).__name__
            if command == "remind_inventory":
                sent = m.InventoryReviewDelivery.objects.filter(status="sent").count() - sent_before
                messages = file_message_count(settings.EMAIL_FILE_PATH) - messages_before
                check("local_review_reminder_delivery", sent > 0 and sent == messages)
            report["workflows"].append(
                {
                    "name": command,
                    "ms": round((perf_counter() - started) * 1000, 1),
                    "queries": profile.count,
                    "result": result,
                }
            )
        save()

        # Actual loopback HTTP, authenticated sessions and full middleware/rendering.
        # This is a diagnostic threaded WSGI server, not a production web-server claim.
        class Server(ThreadingMixIn, WSGIServer):
            daemon_threads = True
            request_queue_size = 128

            def process_request_thread(self, request, client_address):
                try:
                    super().process_request_thread(request, client_address)
                finally:
                    from django.db import connections

                    connections.close_all()

        class QuietHandler(WSGIRequestHandler):
            def log_message(self, *args):
                pass

        server = Server(("127.0.0.1", 0), QuietHandler)
        server.set_app(get_wsgi_application())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{server.server_port}"
        national_names = {
            "company_overview",
            "national_shell",
            "national_summary",
            "national_versions",
            "national_problems",
            "national_activity",
        }
        cases = [
            (name, role, url, method, data)
            for name, role, method, url, data in endpoints(org, asset)
            if options["http_profile"] == "full"
            or (options["http_profile"] == "company" and role == "owner")
            or (options["http_profile"] == "national" and name in national_names)
        ]
        # Obtain ordinary CSRF cookies before real HTTP POST research requests.
        clients["analyst"].get("/circl/research/")
        cookies = {
            role: "; ".join(f"{key}={value.value}" for key, value in client.cookies.items())
            for role, client in clients.items()
        }
        csrf = {
            role: client.cookies.get("csrftoken").value if client.cookies.get("csrftoken") else ""
            for role, client in clients.items()
        }

        owner_fixtures = []
        for membership in (
            m.Membership.objects.filter(
                role="admin",
                user__username__startswith="scale-owner-",
                organization__operator_visibility=True,
            )
            .select_related("user", "organization")
            .order_by("organization_id")[: options["concurrency"]]
        ):
            fixture_client = Client(raise_request_exception=False)
            fixture_client.force_login(membership.user)
            fixture_client.get("/register/")
            first_asset = membership.organization.assets.order_by("name", "pk").first()
            owner_fixtures.append(
                {
                    "cookie": "; ".join(
                        f"{key}={value.value}" for key, value in fixture_client.cookies.items()
                    ),
                    "csrf": fixture_client.cookies.get("csrftoken").value
                    if fixture_client.cookies.get("csrftoken")
                    else "",
                    "slug": membership.organization.slug,
                    "asset": str(first_asset.pk),
                }
            )

        def fetch(index_case):
            index, case = index_case
            name, role, url, method, data = case
            token = csrf[role]
            cookie = cookies[role]
            if role == "owner" and owner_fixtures:
                fixture = owner_fixtures[index % len(owner_fixtures)]
                url = url.replace(org.slug, fixture["slug"]).replace(str(asset.pk), fixture["asset"])
                cookie, token = fixture["cookie"], fixture["csrf"]
            headers = {"Cookie": cookie}
            body = None
            if method == "post":
                headers.update({"X-CSRFToken": token, "Content-Type": "application/x-www-form-urlencoded"})
                body = urllib.parse.urlencode(data).encode()
            request = urllib.request.Request(origin + url, headers=headers, data=body, method=method.upper())
            started = perf_counter()
            try:
                response = urllib.request.urlopen(request, timeout=25)
            except urllib.error.HTTPError as error:
                response = error
            except Exception as error:
                return {
                    "name": name,
                    "status": 0,
                    "ms": round((perf_counter() - started) * 1000, 1),
                    "error": type(error).__name__,
                }
            response.read()
            response.close()
            return {
                "name": name,
                "status": response.code,
                "ms": round((perf_counter() - started) * 1000, 1),
                "queries": int(response.headers.get("X-Scale-Queries", "0")),
                "guard": response.headers.get("X-Scale-Guard"),
            }

        churn_stop = threading.Event()
        churn_errors = []
        churn_updates = []
        churn_refreshes = []
        churn_target = None
        churn_threads = []
        if options.get("churn"):
            churn_target = (
                m.Installation.objects.filter(asset__organization=org, version="2.14.1").first()
                or m.Installation.objects.filter(asset__organization=org).first()
            )
            churn_original = churn_target.version

            def mutate():
                close_old_connections()
                try:
                    while not churn_stop.wait(0.1):
                        m.Installation.objects.filter(pk=churn_target.pk).update(
                            version="9.99.99" if len(churn_updates) % 2 == 0 else churn_original
                        )
                        churn_updates.append(1)
                except Exception as error:
                    churn_errors.append(type(error).__name__)
                finally:
                    connection.close()

            def rebuild():
                from .national_snapshots import refresh_pending

                close_old_connections()
                try:
                    while not churn_stop.wait(0.25):
                        churn_refreshes.append(refresh_pending(limit=50, batch_size=50))
                except Exception as error:
                    churn_errors.append(type(error).__name__)
                finally:
                    connection.close()

            churn_threads = [
                threading.Thread(target=mutate, daemon=True),
                threading.Thread(target=rebuild, daemon=True),
            ]
            for worker in churn_threads:
                worker.start()
        try:
            # Do not flood endpoints already known to exceed the diagnostic guard.
            serial_status = {i["name"]: i["samples"][-1]["status"] for i in report["serial"]}
            healthy = [c for c in cases if serial_status[c[0]] == 200]
            total = healthy * options["http_repeats"]
            started = perf_counter()
            with concurrent.futures.ThreadPoolExecutor(max_workers=options["concurrency"]) as pool:
                results = list(pool.map(fetch, enumerate(total)))
            duration = perf_counter() - started
            latencies = sorted(r["ms"] for r in results)
            report["http"] = {
                "concurrency": options["concurrency"],
                "profile": options["http_profile"],
                "repeats_per_route": options["http_repeats"],
                "owner_identities": len(owner_fixtures),
                "requests": len(results),
                "seconds": round(duration, 2),
                "requests_per_second": round(len(results) / duration, 2),
                "p50_ms": round(statistics.median(latencies), 1) if latencies else None,
                "p95_ms": latencies[max(0, math.ceil(len(latencies) * 0.95) - 1)] if latencies else None,
                "failures": sum(r["status"] != 200 for r in results),
                "results": results,
                "excluded_serial_failures": [c[0] for c in cases if serial_status[c[0]] != 200],
            }
        finally:
            churn_stop.set()
            for worker in churn_threads:
                worker.join(35)
            if any(worker.is_alive() for worker in churn_threads):
                raise CommandError("Synthetic churn worker did not stop; inspect owned scale lab")
            if churn_target:
                m.Installation.objects.filter(pk=churn_target.pk).update(version=churn_original)
                from .national_snapshots import refresh_pending

                refresh_pending(limit=500)
                report["churn"] = {
                    "updates": len(churn_updates),
                    "refreshes": sum(churn_refreshes),
                    "errors": churn_errors,
                    "original_version_restored": m.Installation.objects.get(pk=churn_target.pk).version
                    == churn_original,
                }
                check(
                    "concurrent_changes_and_refresh",
                    bool(churn_updates)
                    and bool(sum(churn_refreshes))
                    and not churn_errors
                    and report["churn"]["original_version_restored"],
                )
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            close_old_connections()

        def write_probe(index):
            close_old_connections()
            from django.test import RequestFactory
            from django.contrib.messages.storage.fallback import FallbackStorage
            from django.middleware.csrf import CsrfViewMiddleware
            from .views import create_asset

            request = RequestFactory().post(
                f"/organizations/{org.slug}/assets/new/",
                dict(
                    name=f"SYNTHETIC concurrent write {index}",
                    kind="server",
                    criticality="normal",
                    lifecycle="active",
                    responsible_team="Scale test",
                ),
                HTTP_X_CSRFTOKEN=csrf["owner"],
            )
            request.user = owner
            request.session = {}
            request.COOKIES["csrftoken"] = csrf["owner"]
            request._messages = FallbackStorage(request)
            started = perf_counter()
            try:
                with transaction.atomic():
                    rejected = CsrfViewMiddleware(lambda r: None).process_view(
                        request, create_asset, (), {"slug": org.slug}
                    )
                    response = rejected if rejected is not None else create_asset(request, slug=org.slug)
                    passed = (
                        response.status_code == 302
                        and org.assets.count() == manifest["assets_per_company"] + 1
                    )
                    transaction.set_rollback(True)
                return {
                    "ms": round((perf_counter() - started) * 1000, 1),
                    "passed": passed,
                    "status": response.status_code,
                }
            except Exception as error:
                return {
                    "ms": round((perf_counter() - started) * 1000, 1),
                    "passed": False,
                    "error": type(error).__name__,
                }
            finally:
                connection.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            writes = list(pool.map(write_probe, range(40)))
        report["concurrent_writes"] = {
            "concurrency": 4,
            "requests": 40,
            "failures": sum(not w["passed"] for w in writes),
            "p95_ms": sorted(w["ms"] for w in writes)[37],
            "results": writes,
            "inventory_count_preserved": m.Asset.objects.count()
            == manifest["companies"] * manifest["assets_per_company"],
        }
        check(
            "concurrent_owner_writes",
            report["concurrent_writes"]["failures"] == 0
            and report["concurrent_writes"]["inventory_count_preserved"],
        )
        import uuid

        durable_client = Client(enforce_csrf_checks=True, raise_request_exception=False)
        for key, value in clients["owner"].cookies.items():
            durable_client.cookies[key] = value.value
        marker = "SYNTHETIC committed probe " + uuid.uuid4().hex
        response = durable_client.post(
            f"/organizations/{org.slug}/assets/new/",
            dict(
                name=marker,
                kind="server",
                criticality="normal",
                lifecycle="active",
                responsible_team="Scale test",
            ),
            HTTP_X_CSRFTOKEN=csrf["owner"],
        )
        created = m.Asset.objects.filter(organization=org, name=marker).first()
        check("committed_owner_write", response.status_code == 302 and created is not None)
        if created:
            check(
                "committed_owner_read",
                durable_client.get(f"/organizations/{org.slug}/assets/{created.pk}/").status_code == 200,
            )
            created.delete()  # Only this exact probe identity; preserve the retained fixture.
        from .national_snapshots import refresh_pending

        refresh_pending(limit=500)
        check(
            "committed_probe_cleanup",
            m.Asset.objects.count() == manifest["companies"] * manifest["assets_per_company"],
        )
        report["acceptance_passed"] = (
            all(c["passed"] for c in report["checks"])
            and all(sample["status"] == 200 for row in report["serial"] for sample in row["samples"])
            and report["http"]["failures"] == 0
        )
        save()
    print(
        json.dumps(
            {
                "phase": "complete",
                "report": str(OUTPUT / (options["label"] + ".json")),
                "checks_passed": sum(c["passed"] for c in report["checks"]),
                "checks_total": len(report["checks"]),
                "http": {k: v for k, v in report["http"].items() if k not in {"results"}},
            }
        ),
        flush=True,
    )


def measure_workflows(options):
    """Verify actual reminder outcomes, separately from Django's test environment overrides."""
    import io
    from django.conf import settings
    from django.core.management import call_command

    if (
        settings.EMAIL_BACKEND != "django.core.mail.backends.filebased.EmailBackend"
        or settings.SERVICE_MAIL_TRANSPORT != "file"
    ):
        raise CommandError("Workflows require the local file sink")
    before = m.InventoryReviewDelivery.objects.filter(status="sent").count()
    files_before = len(list(Path(settings.EMAIL_FILE_PATH).glob("*")))
    messages_before = file_message_count(settings.EMAIL_FILE_PATH)
    started = perf_counter()
    profile = RequestProfile(seconds=20, queries=3000)
    with connection.execute_wrapper(profile):
        call_command("remind_inventory", limit=10, stdout=io.StringIO())
    report = {
        "phase": "workflows",
        "reminder_ms": round((perf_counter() - started) * 1000, 1),
        "queries": profile.count,
        "backend": settings.EMAIL_BACKEND,
        "new_sent": m.InventoryReviewDelivery.objects.filter(status="sent").count() - before,
        "new_files": len(list(Path(settings.EMAIL_FILE_PATH).glob("*"))) - files_before,
        "new_messages": file_message_count(settings.EMAIL_FILE_PATH) - messages_before,
        "errors": m.InventoryReviewDelivery.objects.filter(status="error").count(),
    }
    (OUTPUT / "workflow-verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)
    if report["new_sent"] < 1 or report["new_messages"] != report["new_sent"] or report["errors"]:
        raise CommandError("Actual local reminder delivery was not confirmed")


def file_message_count(directory):
    # Django may append multiple messages to one sink file; file count is not mail count.
    import re

    return sum(
        len(re.findall(rb"(?m)^Message-ID:", path.read_bytes()))
        for path in Path(directory).glob("*")
        if path.is_file()
    )
