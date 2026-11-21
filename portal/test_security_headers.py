"""Default browser boundaries must not remove the explicit integration frame policy."""

from django.http import HttpResponse, JsonResponse
from django.test import SimpleTestCase, RequestFactory
from .security_headers import BrowserPolicy


class BrowserPolicyTests(SimpleTestCase):
    def test_documents_block_inline_scripts_and_third_party_connections(self):
        response = BrowserPolicy(lambda request: HttpResponse("<html></html>"))(RequestFactory().get("/"))
        policy = response["Content-Security-Policy"]
        self.assertIn("script-src 'self';", policy)
        self.assertIn("connect-src 'self';", policy)
        self.assertIn("frame-ancestors 'none';", policy)
        self.assertIn("object-src 'none';", policy)
        self.assertNotIn("'unsafe-eval'", policy)
        self.assertIn("geolocation=()", response["Permissions-Policy"])

    def test_explicit_approved_frame_policy_is_preserved(self):
        response = HttpResponse("<html></html>")
        policy = "frame-src https://approved.example; frame-ancestors 'none'"
        response["Content-Security-Policy"] = policy
        result = BrowserPolicy(lambda request: response)(RequestFactory().get("/applications/"))
        self.assertEqual(result["Content-Security-Policy"], policy)

    def test_api_responses_are_not_reinterpreted_as_documents(self):
        response = BrowserPolicy(lambda request: JsonResponse({"ok": True}))(RequestFactory().get("/api/"))
        self.assertNotIn("Content-Security-Policy", response)
