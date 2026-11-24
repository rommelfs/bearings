"""User paths preserve selected work, evidence meaning and current access boundaries."""

import re
from html import unescape
from urllib.parse import parse_qs, urlencode, urlsplit
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse
from django.utils.html import escape
from .tests import Fixture
from .models import Asset, AssetIssue, Finding, SourceRecord
from . import issues
from .queue_context import return_url


class ReturnContextTests(SimpleTestCase):
    def test_only_local_list_destinations_and_known_filters_survive(self):
        factory = RequestFactory()
        for target in [
            "https://evil.invalid/issues/",
            "//evil.invalid/issues/",
            "/accounts/logout/",
            "/issues/\\evil",
            "/issues/#fragment",
            "/issues/\nnext",
            "javascript:alert(1)",
        ]:
            with self.subTest(target=target):
                self.assertEqual(return_url(factory.get("/", {"return_to": target})), "")
        self.assertEqual(
            return_url(factory.get("/", {"return_to": "/issues/?q=MISP&state=active&secret=discard"})),
            "/issues/?q=MISP&state=active",
        )


class UsabilityPathsTests(Fixture):
    def setUp(self):
        self.login()

    def vulnerability(self, severity, suffix):
        record = SourceRecord.objects.create(
            organization=self.a,
            source="fixture://usability",
            external_id=f"CVE-2026-{suffix}",
            source_severity=severity,
            payload={
                "containers": {
                    "cna": {
                        "metrics": [
                            {
                                "cvssV3_1": {
                                    "version": "3.1",
                                    "baseScore": 9.3 if severity == "critical" else 5.3,
                                }
                            }
                        ]
                    }
                }
            },
            shareable=True,
        )
        finding = Finding.objects.create(
            organization=self.a,
            installation=self.installation,
            record=record,
            explanation="Synthetic evidence needs assessment",
        )
        return issues.ensure_vulnerability_issue(finding)

    def test_group_filter_survives_applying_filters_and_is_named_even_with_no_results(self):
        issue = self.vulnerability("critical", "10001")
        params = {
            "organization": self.a.slug,
            "group_issue": str(issue.pk),
            "product": str(self.product.pk),
            "kind": "vulnerability",
            "state": "active",
        }
        response = self.client.get(reverse("issues"), params)
        self.assertContains(response, f"Software group: {self.product.name}")
        self.assertContains(response, f'name="group_issue" value="{issue.pk}"')
        self.assertContains(response, f'name="product" value="{self.product.pk}"')
        self.assertEqual(response.context["counts"]["total"], 1)
        response = self.client.get(reverse("issues"), {**params, "q": "no-such-machine"})
        self.assertContains(response, f"Software group: {self.product.name}")
        chip = next(c for c in response.context["active_filters"] if c["label"].startswith("Software group:"))
        remaining = parse_qs(urlsplit(chip["url"]).query)
        self.assertNotIn("group_issue", remaining)
        self.assertNotIn("product", remaining)
        self.assertEqual(remaining["q"], ["no-such-machine"])

    def test_critical_source_review_precedes_newer_medium_record_with_same_task_priority(self):
        critical = self.vulnerability("critical", "10001")
        medium = self.vulnerability("medium", "10002")
        self.assertEqual(critical.priority, medium.priority)
        response = self.client.get(reverse("issues"), {"organization": self.a.slug})
        self.assertEqual([row.pk for row in response.context["page"]], [critical.pk, medium.pk])

    def test_filtered_list_detail_action_and_saved_return_keep_context(self):
        issue = issues.save_issue(
            self.admin,
            AssetIssue(organization=self.a),
            {
                "asset": self.asset,
                "kind": "support",
                "title": "Support review",
                "source_label": "Fixture",
                "evidence_text": "Synthetic support evidence",
            },
            "Synthetic local evidence",
        )
        target = (
            reverse("issues") + "?" + urlencode({"organization": self.a.slug, "kind": "support", "page": 2})
        )
        query = "?" + urlencode({"return_to": target})
        detail = self.client.get(self.url("issue", pk=issue.pk) + query)
        self.assertContains(detail, escape(target))
        self.assertContains(detail, "Back to filtered list")
        action = self.url("company-action", pk=issue.pk) + query
        form = self.client.get(action).context["form"]
        response = self.client.post(
            action,
            {
                "operation": "assign",
                "owner_team": "Infrastructure",
                "note": "Assigned after evidence review",
                "token": form.initial["token"],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(parse_qs(urlsplit(response.url).query)["return_to"], [target])
        self.assertContains(self.client.get(response.url), escape(target))
        issue.refresh_from_db()
        self.assertEqual(issue.owner_team, "Infrastructure")

    def test_guide_keeps_review_filters_through_steps_and_saved_assessment(self):
        finding = self.record_finding()
        target = reverse("home") + "?state=action&severity=critical&q=Example"
        query = "?" + urlencode({"return_to": target, "step": "evidence"})
        response = self.client.get(self.url("case-guide", pk=finding.pk) + query)
        self.assertContains(response, escape(target))
        links = [
            parse_qs(urlsplit(unescape(link)).query)
            for link in re.findall(r'href="([^"]+)"', response.content.decode())
        ]
        steps = [link for link in links if "step" in link]
        self.assertTrue(steps)
        self.assertTrue(all(link.get("return_to") == [target] for link in steps))
        post = (
            self.url("finding-review", pk=finding.pk)
            + "?"
            + urlencode({"return": "guide", "return_to": target})
        )
        response = self.client.post(
            post, {"status": "under_review", "assessment": "unknown", "reason": "Awaiting vendor evidence"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(parse_qs(urlsplit(response.url).query)["return_to"], [target])
        self.assertEqual(parse_qs(urlsplit(response.url).query)["step"], ["risk"])

    def badge_links(self, response):
        return [
            unescape(link)
            for link in re.findall(
                r'<a class="severity-badge[^\"]*" href="([^\"]+)"', response.content.decode()
            )
        ]

    def test_rating_badges_keep_filters_and_evidence_anchor_through_return(self):
        finding = self.vulnerability("critical", "10001").finding
        score_payload = finding.record.payload
        variants = [
            (score_payload, "critical", 1),
            (
                {
                    **score_payload,
                    "bearings_distro": {
                        "schema": "bearings.distro-oval.v1",
                        "severity": "high",
                        "feed": "ubuntu:24.04",
                    },
                },
                "high",
                2,
            ),
            ({}, "unknown", 1),
        ]
        for payload, severity, expected_badges in variants:
            with self.subTest(severity=severity):
                finding.record.payload = payload
                finding.record.save()
                target = (
                    reverse("home")
                    + "?"
                    + urlencode({"state": "action", "q": "Example", "severity": severity, "review_page": 1})
                )
                response = self.client.get(target)
                links = self.badge_links(response)
                self.assertEqual(len(links), expected_badges)
                for link in links:
                    parsed = urlsplit(link)
                    self.assertEqual(parsed.fragment, f"evidence-{finding.pk}")
                    self.assertEqual(parse_qs(parsed.query)["finding"], [str(finding.pk)])
                    self.assertEqual(parse_qs(parsed.query)["return_to"], [target])
                    detail = self.client.get(link)
                    self.assertContains(detail, f'id="evidence-{finding.pk}"')
                    self.assertContains(detail, f'href="{escape(target)}">← Back to filtered list')
                    # Clicking the rating again must not nest the evidence URL in return_to.
                    for repeated in self.badge_links(detail):
                        self.assertEqual(parse_qs(urlsplit(repeated).query)["return_to"], [target])

    def test_guided_rating_badge_preserves_original_list_instead_of_guide_url(self):
        finding = self.vulnerability("critical", "10001").finding
        target = reverse("home") + "?state=action&q=Example&severity=critical"
        response = self.client.get(
            self.url("case-guide", pk=finding.pk), {"step": "evidence", "return_to": target}
        )
        links = self.badge_links(response)
        self.assertEqual(len(links), 1)
        self.assertEqual(parse_qs(urlsplit(links[0]).query)["return_to"], [target])
        self.assertContains(self.client.get(links[0]), escape(target))
        direct = self.client.get(self.url("case-guide", pk=finding.pk), {"step": "evidence"})
        self.assertNotIn("return_to", parse_qs(urlsplit(self.badge_links(direct)[0]).query))
        unsafe = self.client.get(
            self.url("case-guide", pk=finding.pk),
            {"step": "evidence", "return_to": "https://evil.invalid/reviews/"},
        )
        self.assertNotIn("return_to", parse_qs(urlsplit(self.badge_links(unsafe)[0]).query))

    def test_assigned_addresses_appear_in_issue_and_guide_without_foreign_assignments(self):
        self.asset.object_type = "virtualization.virtualmachine"
        self.asset.save()
        finding = self.record_finding()
        issue = issues.ensure_vulnerability_issue(finding)
        for org, source, name in [(self.a, self.sa, "192.0.2.20/24"), (self.b, self.sb, "198.51.100.99/24")]:
            Asset.objects.create(
                organization=org,
                source=source,
                network_host=self.asset,
                name=name,
                kind="ip_address",
                object_type="ipam.ipaddress",
            )
        for route, pk in [("issue", issue.pk), ("case-guide", finding.pk)]:
            with self.subTest(route=route):
                response = self.client.get(self.url(route, pk=pk))
                self.assertContains(response, "192.0.2.20/24")
                self.assertNotContains(response, "198.51.100.99")
                self.assertNotContains(response, "Primary IP / network")

    def test_return_context_never_broadens_issue_read_authorization(self):
        issue = self.vulnerability("critical", "10001")
        self.login(self.reader)
        response = self.client.get(
            self.url("issue", pk=issue.pk), {"return_to": "/issues/?organization=beta"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/issues/?organization=beta").status_code, 404)
        self.assertEqual(
            self.client.get(
                self.url("issue", org=self.b, pk=issue.pk), {"return_to": "/issues/"}
            ).status_code,
            404,
        )
