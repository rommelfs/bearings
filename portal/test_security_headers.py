"""Default browser boundaries must not remove the explicit integration frame policy."""

from django.http import HttpResponse, JsonResponse
from django.test import SimpleTestCase, RequestFactory, override_settings
from django.core.exceptions import ImproperlyConfigured
from types import SimpleNamespace
from .map_configuration import map_options
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

    @override_settings(MAP_TILE_URL="https://geo.circl.lu/hot/{z}/{x}/{y}.png")
    def test_tiles_only_extend_images_on_map_documents(self):
        for name in ("circl-overview", "circl-map-location", "organization"):
            request = RequestFactory().get("/")
            request.resolver_match = SimpleNamespace(url_name=name)
            response = BrowserPolicy(lambda r: HttpResponse("<html></html>"))(request)
            policy = response["Content-Security-Policy"]
            self.assertEqual("geo.circl.lu" in policy, name != "organization")
            self.assertIn("connect-src 'self';", policy)
            self.assertIn("script-src 'self';", policy)

    @override_settings(MAP_TILE_URL="")
    def test_disabled_tiles_keep_local_policy(self):
        self.assertEqual(map_options()["map_tile_url"], "")

    def test_operator_tile_template_cannot_inject_policy_or_credentials(self):
        for value in (
            "http://geo.example/{z}/{x}/{y}.png",
            "https://user:secret@geo.example/{z}/{x}/{y}.png",
            "https://geo.example/{z}/{x}/{y}.png?q=secret",
            "https://geo.example/{z}/{x}/{y}; script-src *",
            "https://{z}.example/{x}/{y}.png",
            "https://geo.example:invalid/{z}/{x}/{y}.png",
            "https://geo.example/{q}/{x}/{y}.png",
        ):
            with override_settings(MAP_TILE_URL=value), self.assertRaises(ImproperlyConfigured):
                map_options()
