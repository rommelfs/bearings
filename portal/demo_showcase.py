"""Deterministic, explicitly fictional exploration data. No connector, scan or delivery I/O."""

from datetime import timedelta
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from . import issues, plum
from .access import audit, require
from .demo_data import KEY, capture
from .intelligence import digest
from .models import (
    Asset,
    AssetIssue,
    Contact,
    DemoDataset,
    FindingHistory,
    FlowIntelCase,
    FlowIntelInstance,
    FlowIntelTask,
    InfrastructureClaim,
    Installation,
    InventorySource,
    IssueRiskLink,
    Membership,
    MOSPSource,
    MOSPRisk,
    MOSPRiskRevision,
    NotificationBatch,
    NotificationDelivery,
    NotificationDeliveryFinding,
    Organization,
    PlumInstance,
    Product,
    RiskLink,
    RTInstance,
    RTTicket,
)
from .services import persist_lookup

COMPANIES = [
    "Aster Finance",
    "Boreal Care",
    "Cobalt Logistics",
    "Dune Energy",
    "Ember Manufacturing",
    "Fjord Research",
    "Grove Retail",
    "Harbor Municipality",
    "Iris Hosting",
    "Juniper Education",
]
PRODUCTS = [
    ("Apache Log4j", "2.14.1", "CVE-2021-44228", 10.0),
    ("Microsoft Exchange Server", "2019 CU12", "CVE-2022-41082", 9.8),
    ("Fortinet FortiOS", "7.2.3", "CVE-2023-27997", 8.1),
    ("OpenSSH", "9.2p1", "CVE-2024-6387", 5.9),
    ("Example application", "", "DEMO-UNKNOWN-0001", None),
    ("Example firmware", "1.4.0", "DEMO-LOW-0002", 3.1),
]
SCENARIOS = [
    (
        "Service disruption",
        "Availability",
        "Customer-facing service",
        "Unpatched or unsupported component",
        "A failure could interrupt customer operations and breach service commitments.",
    ),
    (
        "Unauthorized disclosure",
        "Confidentiality",
        "Business information",
        "Insufficient access control",
        "Unauthorized access could expose sensitive data and require an incident assessment.",
    ),
    (
        "Unauthorized modification",
        "Integrity",
        "Business application",
        "Exposed management interface",
        "An exposed interface could permit configuration or data changes.",
    ),
    (
        "Recovery delay",
        "Availability",
        "Infrastructure",
        "Expired support or warranty",
        "Unavailable support or replacement parts could lengthen recovery.",
    ),
    (
        "License interruption",
        "Availability",
        "Software entitlement",
        "Unverified license renewal",
        "An entitlement interruption could disrupt an essential workflow.",
    ),
    (
        "Unexpected network service",
        "Integrity",
        "Network perimeter",
        "Unreviewed service exposure",
        "A newly observed port warrants checking configuration and operational intent.",
    ),
]


def payload(cve, title, score):
    cna = {"title": "SYNTHETIC EXERCISE · " + title}
    if score is not None:
        cna["metrics"] = [{"cvssV3_1": {"version": "3.1", "baseScore": score}}]
    return {
        "fixture": True,
        "note": "Invented demonstration severity/applicability, not a live Vulnerability-Lookup record. No exploitation or compromise is asserted.",
        "cveMetadata": {"cveId": cve},
        "containers": {"cna": cna},
    }


@transaction.atomic
def seed(actor, *, companies=10, assets_per_company=30, restore=False):
    require(actor.is_active and actor.is_superuser)
    if not settings.DEBUG:
        raise ValidationError(
            "Synthetic data creation requires DEBUG; removal remains available without DEBUG"
        )
    if (
        not 1 <= companies <= 20
        or not 2 <= assets_per_company <= 100
        or companies * assets_per_company > 1000
    ):
        raise ValidationError("Use 1–20 companies, 2–100 assets per company, at most 1,000 assets")
    dataset, new = DemoDataset.objects.get_or_create(key=KEY)
    dataset = DemoDataset.objects.select_for_update().get(pk=dataset.pk)
    if dataset.state == "removed" and not restore:
        return dataset, False
    if not new and dataset.state == "active" and dataset.entries.exists():
        return dataset, False
    if dataset.state == "removed":
        dataset.state, dataset.removed_at = "active", None
    dataset.configuration = {
        "companies": companies,
        "assets_per_company": assets_per_company,
        "anchor": timezone.now().isoformat(),
        "version": 1,
    }
    dataset.save()
    now, today = timezone.now(), timezone.localdate()
    with capture(dataset):
        catalog = MOSPSource.objects.create(
            name="SYNTHETIC exploration risk catalog",
            base_url="https://mosp.demo.example.invalid",
            publisher="SYNTHETIC — not MONARC evidence",
            enabled=False,
        )
        revisions = []
        for idx, (name, threat, asset_type, weakness, consequence) in enumerate(SCENARIOS):
            risk_data = {
                "uuid": str(uuid.uuid5(uuid.NAMESPACE_URL, "bearings-demo-risk/" + str(idx))),
                "id": idx + 1,
                "description": "SYNTHETIC · " + name,
                "license": "CC0-1.0",
                "fixture": True,
            }
            bundle = {
                "risk": risk_data,
                "asset": {"name": asset_type},
                "threat": {"name": threat},
                "vulnerability": {"name": weakness},
                "fixture": True,
                "note": "Invented MOSP-shaped example; no upstream assessment or risk rating.",
            }
            risk = MOSPRisk.objects.create(
                source=catalog,
                uuid=risk_data["uuid"],
                external_id=idx + 1,
                description=risk_data["description"],
                payload=risk_data,
                content_hash=digest(risk_data),
            )
            revision = MOSPRiskRevision.objects.create(
                risk=risk, payload=bundle, content_hash=digest(bundle), risk_hash=digest(risk_data)
            )
            risk.current_revision = revision
            risk.save(update_fields=["current_revision"])
            revisions.append(revision)
        exposure = PlumInstance.objects.create(
            name="SYNTHETIC exploration exposure history",
            base_url="https://plum.demo.example.invalid",
            enabled=True,
            fixture=True,
        )
        orgs, focus_issues, focus_findings = [], [], []
        for c in range(companies):
            company_name = COMPANIES[c % len(COMPANIES)] + (f" {c + 1}" if c >= len(COMPANIES) else "")
            org = Organization.objects.create(
                slug=f"demo-explore-{c + 1:02}",
                name=company_name + " (SYNTHETIC)",
                operator_visibility=c % 5 != 4,
            )
            orgs.append(org)
            source = InventorySource.objects.create(
                organization=org, mode="development", import_enabled=False
            )
            # Existing local accounts are reused; no passwords, roles or SSO identities are changed.
            from django.contrib.auth import get_user_model

            account = get_user_model().objects.filter(username="company-admin", is_active=True).first()
            if account:
                Membership.objects.create(organization=org, user=account, role="admin")
            for k in range(3):
                Contact.objects.create(
                    organization=org,
                    name=["Security operations", "Infrastructure owner", "Executive escalation"][k]
                    + " (SYNTHETIC)",
                    email=f"team-{k + 1}@company-{c + 1}.example.invalid",
                    role=["Security contact", "Asset owner", "Escalation contact"][k],
                    language=["en", "fr", "de"][k],
                    scope="SYNTHETIC ONLY — no real reachability or authority",
                    availability="Weekdays 09:00–17:00 Europe/Luxembourg (simulated)",
                    escalation_order=k + 1,
                    notification_enabled=False,
                    reviewed_at=now if k != 2 else None,
                    next_review=today + timedelta(days=90) if k != 2 else today - timedelta(days=3),
                )
            # TEST-NET ranges and .invalid names cannot be mistaken for customer scope.
            first_ip = f"198.51.100.{c * 10 + 1}"
            InfrastructureClaim.objects.create(
                organization=org,
                kind="domain",
                value=f"company-{c + 1}.example.invalid",
                status="verified",
                method="SYNTHETIC fixture only",
                reviewed_at=now,
                valid_from=now - timedelta(days=90),
            )
            exposure.organizations.add(org)
            products = [
                Product.objects.create(organization=org, name=name, identifier="demo:product:" + str(p))
                for p, (name, *_rest) in enumerate(PRODUCTS)
            ]
            for a in range(assets_per_company):
                p = a % len(PRODUCTS)
                hostname = f"{['app', 'mail', 'fw', 'ssh', 'db', 'edge'][p]}-{c + 1:02}-{a + 1:03}"
                # Keep unique display addresses even in larger custom datasets via documentation IPv6.
                ipv6 = f"2001:db8:{c + 1:x}::{a + 1:x}/64"
                ip = first_ip if a == 0 else f"192.0.2.{(c * assets_per_company + a) % 250 + 1}"
                asset = Asset.objects.create(
                    organization=org,
                    source=source,
                    name=hostname + " (SYNTHETIC)",
                    kind="appliance" if p in {2, 5} else "vm" if a % 3 == 0 else "server",
                    criticality="high" if a % 4 == 0 else "normal",
                    responsible_team=["Messaging", "Infrastructure", "Network security", "Platform"][a % 4],
                    state="synced",
                    object_type="virtualization.virtualmachine" if a % 3 == 0 else "dcim.device",
                    upstream_data={
                        "fixture": True,
                        "primary_ip4": ip + "/32",
                        "primary_ip4_dns_name": hostname + f".company-{c + 1}.example.invalid",
                        "primary_ip6": ipv6,
                        "primary_ip6_dns_name": hostname + f".company-{c + 1}.example.invalid",
                        "site": {"name": ["DEMO Luxembourg DC", "DEMO Esch DC", "DEMO Recovery DC"][c % 3]},
                        "location": {"name": f"Room {1 + c % 3} / Row {1 + a % 5}"},
                        "rack": {"name": f"DEMO-R{c + 1:02}-{a // 10 + 1:02}"},
                        "position": str(a % 40 + 1),
                        "face": "front",
                        "serial": f"SYN-{c + 1:02}-{a + 1:04}",
                        "asset_tag": f"DEMO-{c + 1:02}-{a + 1:04}",
                        "platform": {"name": PRODUCTS[p][0]},
                    },
                    inventory_seen_at=now - timedelta(hours=a % 72),
                    missing_since=now - timedelta(days=5) if a % 17 == 16 else None,
                    lifecycle="retired" if a % 29 == 28 else "active",
                )
                installs = []
                for offset in range(3):
                    index = (p + offset) % len(products)
                    installs.append(
                        Installation.objects.create(
                            asset=asset,
                            product=products[index],
                            version=PRODUCTS[index][1],
                            build=f"SYNTHETIC-{a + 1}",
                            component_type="firmware" if index == 5 else "software",
                        )
                    )
                name, version, cve, score = PRODUCTS[p]
                finding = persist_lookup(
                    None,
                    installs[0],
                    "fixture://explore-v1/SYNTHETIC",
                    cve,
                    payload(cve, name + " review", score),
                )
                status = ["new", "under_review", "confirmed", "accepted_risk", "resolved", "false_positive"][
                    (a // 6 + c) % 6
                ]
                assessment = ["unknown", "potential", "affected", "affected", "not_affected", "not_affected"][
                    (a // 6 + c) % 6
                ]
                FindingHistory.objects.create(
                    finding=finding,
                    actor=actor,
                    previous_status="new",
                    status=status,
                    previous_assessment="unassessed",
                    assessment=assessment,
                    reason="SYNTHETIC analyst exercise; no live applicability or remediation assertion",
                )
                finding.status, finding.analyst_applicability, finding.priority = (
                    status,
                    assessment,
                    ["critical", "high", "high", "review", "low", "review"][a % 6],
                )
                finding.explanation += " SYNTHETIC reviewed state for exploration only."
                finding.save()
                revision = finding.record.revisions.first()
                RiskLink.objects.create(
                    finding=finding,
                    evidence_revision=revision,
                    risk_revision=revisions[p],
                    reason="SYNTHETIC mapping: " + SCENARIOS[p][4],
                    created_by=actor,
                )
                vuln_issue = finding.asset_issue
                vuln_issue.action_due = today + timedelta(days=(a % 15) - 7)
                vuln_issue.save(update_fields=["action_due"])
                issues.snapshot(vuln_issue, actor)
                if org.operator_visibility and a == 0:
                    focus_findings.append(finding)
                for j in range(2):
                    kind = ["support", "license", "warranty", "eol", "maintenance"][(a + j) % 5]
                    issue = issues.save_issue(
                        actor,
                        AssetIssue(organization=org),
                        {
                            "asset": asset,
                            "kind": kind,
                            "title": f"SYNTHETIC · {kind.title()} review · {hostname}",
                            "priority": ["critical", "high", "review", "low"][(a + j) % 4],
                            "status": [
                                "new",
                                "under_review",
                                "confirmed",
                                "accepted_risk",
                                "resolved",
                                "false_positive",
                            ][(a + j) % 6],
                            "source_label": "SYNTHETIC contract and lifecycle evidence",
                            "evidence_text": "Invented contract, dates and vendor assumptions for a demonstration. Validate real evidence before operational use.",
                            "event_date": today + timedelta(days=((a * 7 + j * 19) % 120) - 35),
                            "action_due": today + timedelta(days=(a + j) % 45 - 15),
                            "owner_team": asset.responsible_team,
                            "consequence": SCENARIOS[(a + j) % 6][4],
                            "next_action": "Verify entitlement and exposure, assign an owner, agree a deadline and record remediation evidence.",
                            "shareable": a % 7 != 6,
                            "operator_only": a % 13 == 12,
                            "fact_status": ["unverified", "verified", "disputed", "unknown"][a % 4],
                        },
                        "SYNTHETIC reviewed lifecycle example; no real vendor assertion",
                    )
                    IssueRiskLink.objects.create(
                        issue=issue,
                        issue_revision=issue.revisions.first(),
                        risk_revision=revisions[(a + j) % 6],
                        reason="SYNTHETIC possible consequence, not a calculated risk score",
                        created_by=actor,
                    )
                    if org.operator_visibility and a == 0 and j == 0:
                        focus_issues.append(issue)
                if a < 3:
                    InfrastructureClaim.objects.create(
                        organization=org,
                        kind="ip",
                        value=ip,
                        status="verified",
                        method="SYNTHETIC documentation address assignment",
                        reviewed_at=now,
                        valid_from=now - timedelta(days=90),
                    )
                    for w in range(6):
                        begin = now - timedelta(days=42 - w * 7)
                        stop = begin + timedelta(days=7)
                        ports = [443] + ([22] if w < 3 else [3389]) + ([8443] if w >= 4 else [])
                        observation = plum.ingest(
                            actor,
                            org,
                            exposure,
                            {
                                "result": {
                                    "ip": ip,
                                    "start": begin.isoformat(),
                                    "stop": stop.isoformat(),
                                    "report_count": 2,
                                    "ports": [
                                        {
                                            "port": port,
                                            "protocol": "tcp",
                                            "tags": ["SYNTHETIC:exploration"],
                                            "first_seen": begin.isoformat(),
                                            "last_seen": stop.isoformat(),
                                        }
                                        for port in ports
                                    ],
                                }
                            },
                            asset=asset,
                        )
                        if w in {3, 4}:
                            port = 3389 if w == 3 else 8443
                            review = plum.create_review(
                                actor,
                                observation,
                                port,
                                "tcp",
                                "",
                                "SYNTHETIC port-change review; no misconfiguration or malware is inferred",
                            )
                            issues.save_issue(
                                actor,
                                review,
                                {"title": "SYNTHETIC · " + review.title, "consequence": SCENARIOS[5][4]},
                                "SYNTHETIC exposure exercise",
                            )
            _notification_preview(actor, org)
        _workflows(actor, focus_issues, focus_findings)
    audit(actor, None, "demo.seeded", dataset.key, configuration=dataset.configuration)
    return dataset, True


def _notification_preview(actor, org):
    from .notifications import message_snapshot

    batch = NotificationBatch.objects.create(
        creator=actor,
        organization=org,
        mode="company",
        transport="file",
        filters={"synthetic_preview_only": True},
        subject_template="SYNTHETIC · {{ finding_count }} reviews · {{ organization }}",
        body_template="SYNTHETIC PREVIEW ONLY — no message has been sent.\nHello {{ contact_name }},\n{{ findings }}\n{{ action }}",
    )
    findings = list(
        org.findings.filter(status__in=["new", "under_review", "confirmed"]).select_related(
            "installation__asset__source__instance", "installation__product", "record"
        )[:4]
    )
    for contact in org.contacts.all()[:2]:
        snapshot, _, subject, body = message_snapshot(
            "company", contact, findings, batch.subject_template, batch.body_template
        )
        snapshot["synthetic_preview_only"] = True
        delivery = NotificationDelivery.objects.create(
            batch=batch,
            organization=org,
            contact=contact,
            snapshot=snapshot,
            fingerprint=digest(snapshot),
            subject=subject,
            body=body,
        )
        for finding in findings:
            NotificationDeliveryFinding.objects.create(delivery=delivery, finding=finding)


def _workflows(actor, issue_rows, findings):
    # Offline previews only. No remote identities, credentials, approval or connector jobs.
    rt = RTInstance.objects.create(
        name="SYNTHETIC offline RTIR previews",
        product="rtir",
        base_url="https://rtir.demo.example.invalid",
        queue_id=2,
        incident_queue_id=1,
        token_env_var="RT_DEMO_OFFLINE_TOKEN",
        enabled=False,
    )
    for n in range(min(3, len(issue_rows))):
        issue = issue_rows[n]
        parent = RTTicket.objects.create(
            instance=rt,
            issue=issue,
            creator=actor,
            role="incident",
            snapshot={"fixture": True},
            fingerprint=digest({"fixture": True, "incident": n}),
            subject=f"SYNTHETIC · Coordinated response exercise {n + 1}",
            content="Offline Incident preview; no remote RTIR ticket exists.",
            reason="Synthetic coordination exploration only",
        )
        for offset in range(min(3, len(issue_rows))):
            target = issue_rows[(n + offset) % len(issue_rows)]
            if RTTicket.objects.filter(instance=rt, issue=target, role="investigation").exists():
                continue
            RTTicket.objects.create(
                instance=rt,
                issue=target,
                creator=actor,
                role="investigation",
                incident=parent,
                snapshot={"fixture": True},
                fingerprint=digest({"fixture": True, "issue": str(target.pk)}),
                subject="SYNTHETIC · Investigate " + target.asset.name,
                content="Offline Investigation preview; no remote RTIR ticket exists.",
                reason="Synthetic preview, no approval or API export",
            )
    flow = FlowIntelInstance.objects.create(
        name="SYNTHETIC offline FlowIntel previews",
        base_url="https://flowintel.demo.example.invalid",
        token_env_var="FLOWINTEL_DEMO_OFFLINE_TOKEN",
        service_org_id=1,
        enabled=False,
    )
    for finding in findings[:4]:
        case = FlowIntelCase.objects.create(
            instance=flow,
            finding=finding,
            creator=actor,
            snapshot={"fixture": True},
            fingerprint=digest({"fixture": True, "finding": finding.pk}),
            title="SYNTHETIC · " + finding.installation.asset.name,
            description="Offline case preview; no FlowIntel case or task has been exported.",
            reason="Synthetic triage workflow",
        )
        for step, title in enumerate(
            ["Validate applicability", "Identify owner and contact", "Plan mitigation", "Verify remediation"],
            1,
        ):
            FlowIntelTask.objects.create(
                case=case, step=step, title=title, description="SYNTHETIC task; no real remediation assertion"
            )
