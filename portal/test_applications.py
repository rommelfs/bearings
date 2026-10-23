"""Browser workspaces must not turn connection metadata into an authorization proxy."""

from django.test import override_settings
from django.urls import reverse
from .browser_policy import browser_base, origin
from .models import AuditEvent, FlowIntelInstance, NetBoxInstance, RTInstance
from .tests import Fixture
from config.oidc import ApprovedOpenIdConnect
from social_core.exceptions import AuthForbidden


@override_settings(
    CANVAS_ORIGIN="https://testserver", CANVAS_FRAME_ORIGINS=["https://netbox.example.invalid"]
)
class ApplicationWorkspaceTests(Fixture):
    def setUp(self):
        self.netbox = NetBoxInstance.objects.create(
            name="Company inventory",
            base_url="https://private-api.example.invalid",
            browser_url="https://netbox.example.invalid",
            token_env_var="NETBOX_PRIVATE_TOKEN",
            access_mode="read_only",
        )
        self.foreign = NetBoxInstance.objects.create(
            name="Hidden foreign inventory",
            base_url="https://other-api.example.invalid",
            browser_url="https://other.example.invalid",
            token_env_var="NETBOX_OTHER_TOKEN",
        )
        self.sa.instance = self.netbox
        self.sa.save()
        self.sb.instance = self.foreign
        self.sb.save()
        self.flow = FlowIntelInstance.objects.create(
            name="CIRCL FlowIntel",
            base_url="https://flow-api.example.invalid",
            browser_url="https://flow.example.invalid",
            token_env_var="FLOWINTEL_PRIVATE_TOKEN",
            service_org_id=3,
        )
        self.company_rt = RTInstance.objects.create(
            name="Company RT",
            base_url="https://rt-api.example.invalid",
            browser_url="https://rt.example.invalid",
            token_env_var="RT_COMPANY_TOKEN",
            organization=self.a,
            enabled=True,
            queue_id=1,
        )
        self.rtir = RTInstance.objects.create(
            name="CIRCL RTIR",
            base_url="https://rt-api.example.invalid",
            browser_url="https://rt.example.invalid",
            token_env_var="RT_CIRCL_TOKEN",
            enabled=True,
            queue_id=2,
            product="rtir",
            incident_queue_id=3,
        )
        self.path = reverse("application", args=[f"netbox-{self.netbox.pk}"])

    def test_directory_visibility_and_connection_metadata_are_scoped(self):
        self.login(self.reader)
        response = self.client.get(reverse("applications"), secure=True)
        self.assertContains(response, "Company inventory")
        self.assertContains(response, "Company RT")
        for hidden in [
            "Hidden foreign inventory",
            "CIRCL FlowIntel",
            "CIRCL RTIR",
            "NETBOX_PRIVATE_TOKEN",
            "private-api.example.invalid",
            "RT_COMPANY_TOKEN",
        ]:
            self.assertNotContains(response, hidden)
        foreign_path = reverse("application", args=[f"netbox-{self.foreign.pk}"])
        self.assertEqual(self.client.get(foreign_path, secure=True).status_code, 404)
        self.assertEqual(
            self.client.get(
                reverse("application", args=[f"flowintel-{self.flow.pk}"]), secure=True
            ).status_code,
            404,
        )

    def test_frame_is_explicit_sandboxed_and_limited_to_the_approved_origin(self):
        self.login()
        response = self.client.get(self.path, secure=True)
        self.assertNotContains(response, "<iframe")
        response = self.client.get(self.path, {"show": "1", "url": "https://evil.invalid"}, secure=True)
        self.assertContains(response, "<iframe")
        self.assertContains(response, 'src="https://netbox.example.invalid/"')
        self.assertContains(
            response, 'sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-downloads"'
        )
        self.assertNotContains(response, "evil.invalid")
        self.assertIn("frame-src https://netbox.example.invalid;", response["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", response["Content-Security-Policy"])
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(self.client.post(self.path, secure=True).status_code, 405)

    def test_unapproved_and_same_origin_apps_stay_in_a_separate_tab(self):
        self.login()
        with override_settings(CANVAS_FRAME_ORIGINS=[]):
            response = self.client.get(self.path, {"show": "1"}, secure=True)
            self.assertNotContains(response, "<iframe")
            self.assertContains(response, "no approved embedding policy")
            self.assertIn("frame-src 'none'", response["Content-Security-Policy"])
        self.netbox.browser_url = "https://testserver"
        self.netbox.save()
        with override_settings(CANVAS_FRAME_ORIGINS=["https://testserver"]):
            self.assertNotContains(self.client.get(self.path, {"show": "1"}, secure=True), "<iframe")
            self.netbox.browser_url = "https://TESTSERVER:00443"
            self.netbox.save()
            self.assertNotContains(self.client.get(self.path, {"show": "1"}, secure=True), "<iframe")

    def test_canonical_redirect_never_uses_caller_urls_or_host_headers(self):
        self.login()
        response = self.client.get(self.path, {"next": "https://evil.invalid", "url": "javascript:bad"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "https://testserver" + self.path)

    def test_operator_visibility_revocation_and_disablement_apply_on_next_request(self):
        self.login(self.analyst)
        response = self.client.get(self.path, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            AuditEvent.objects.filter(
                actor=self.analyst, organization=self.a, action="operator.access"
            ).exists()
        )
        response = self.client.get(reverse("applications"), secure=True)
        self.assertContains(response, "CIRCL FlowIntel")
        self.assertContains(response, "CIRCL RTIR")
        self.a.operator_visibility = False
        self.a.save()
        self.assertEqual(self.client.get(self.path, secure=True).status_code, 404)
        self.login()
        self.netbox.enabled = False
        self.netbox.save()
        self.assertEqual(self.client.get(self.path, secure=True).status_code, 404)

    def test_no_internal_endpoint_fallback_and_login_required(self):
        self.assertEqual(self.client.get(reverse("applications")).status_code, 302)
        self.login()
        self.netbox.browser_url = ""
        self.netbox.save()
        self.assertEqual(self.client.get(self.path, secure=True).status_code, 404)

    def test_origins_reject_unsafe_or_ambiguous_configuration(self):
        for value in [
            "http://netbox.invalid",
            "https://u:p@netbox.invalid",
            "https://netbox.invalid/a",
            "https://netbox.invalid?token=secret",
            "https://netbox.invalid/#fragment",
            "https://netbox.invalid;frame-src",
            "https://netbox.invalid\n",
            "https://netbox.invalid:0",
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                origin(value)
        self.assertEqual(origin("https://netbox.invalid:9443/"), "https://netbox.invalid:9443")
        self.assertEqual(origin("https://NETBOX.invalid:00443"), "https://netbox.invalid")
        self.assertEqual(origin("https://[0:0:0:0:0:0:0:1]:00443"), "https://[::1]")
        for value in ["https://127.1", "https://2130706433", "https://0x7f000001", "https://0177.0.0.1"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                origin(value)
        self.assertEqual(browser_base("https://netbox.invalid/prefix/"), "https://netbox.invalid/prefix")

    def test_lab_always_returns_to_https_without_changing_external_clients(self):
        backend = ApprovedOpenIdConnect.__new__(ApprovedOpenIdConnect)
        backend.setting = lambda name, default=None: (
            "https://localhost:9441/oauth/complete/oidc/" if name == "LAB_CALLBACK" else default
        )
        for current, expected in [
            ("http://localhost:8000/oauth/complete/oidc/", "https://localhost:9441/oauth/complete/oidc/"),
            ("https://localhost:8000/oauth/complete/oidc/", "https://localhost:9441/oauth/complete/oidc/"),
            ("https://localhost:9441/oauth/complete/oidc/", "https://localhost:9441/oauth/complete/oidc/"),
            ("http://127.0.0.1:8000/oauth/complete/oidc/", "https://127.0.0.1:9441/oauth/complete/oidc/"),
            ("https://127.0.0.1:9441/oauth/complete/oidc/", "https://127.0.0.1:9441/oauth/complete/oidc/"),
            ("https://company.invalid/oauth/complete/oidc/", "https://company.invalid/oauth/complete/oidc/"),
        ]:
            backend.redirect_uri = current
            self.assertEqual(backend.get_redirect_uri(), expected)
        backend.redirect_uri = "https://localhost:9441/oauth/complete/oidc/"
        for invalid in [
            "https://evil.invalid/callback",
            "http://localhost:8000/oauth/complete/oidc/",
            "https://:password@localhost:9441/oauth/complete/oidc/",
        ]:
            backend.setting = lambda name, default=None: invalid
            with self.assertRaises(AuthForbidden):
                backend.get_redirect_uri()
