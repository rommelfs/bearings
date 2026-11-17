"""Local diagnostic boundaries and sanitized measurement output."""

import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.test import SimpleTestCase
from scripts import web_timing


class WebTimingTests(SimpleTestCase):
    def test_only_local_synthetic_issuer_and_valid_ports_are_accepted(self):
        manifest = {
            "ports": {"bearings": 8000, "sso": 9444},
            "issuer": "https://localhost:9444/realms/bearings-lab",
        }
        self.assertEqual(
            web_timing.origins(manifest, 9441),
            ("http://localhost:8000", "https://localhost:9441", manifest["issuer"]),
        )
        for invalid in [
            "https://idp.example.invalid/realms/bearings-lab",
            "https://user:password@localhost:9444/realms/bearings-lab",
            manifest["issuer"] + "?secret=synthetic",
        ]:
            with self.subTest(issuer=invalid), self.assertRaises(ValueError):
                web_timing.origins({**manifest, "issuer": invalid}, 9441)
        for port in [0, 65536, True, "9441"]:
            with self.subTest(port=port), self.assertRaises(ValueError):
                web_timing.origins(manifest, port)

    def test_external_and_non_sso_labs_are_refused_before_reading_secrets(self):
        for state in [{"mode": "external", "sso": True}, {"mode": "bundled", "sso": False}]:
            with (
                self.subTest(state=state),
                patch("scripts.dev.active", return_value=state),
                patch("scripts.dev.run") as run,
            ):
                with self.assertRaises(SystemExit):
                    web_timing.main()
                run.assert_not_called()

    def test_measurements_include_only_known_numeric_timings_and_no_query_strings(self):
        response = SimpleNamespace(
            status=200,
            url="https://localhost:9441/?secret=synthetic-code",
            headers={
                "Server-Timing": "overview;dur=17.5, session;dur=2.0, django;dur=20, database;dur=10, dbmax;dur=4, companies;dur=5, priority;dur=6, render;dur=3, scope;dur=1, secret;dur=123"
            },
            read=Mock(return_value=b"synthetic private body"),
        )
        browser = Mock()
        browser.open.return_value = nullcontext(response)
        with patch("scripts.web_timing.perf_counter", side_effect=[10, 10.03, 10.04]):
            _, path, metrics = web_timing.fetch(browser, "https://localhost:9441/")
        self.assertEqual(path, "/")
        self.assertEqual(
            metrics,
            {
                "status": 200,
                "ttfb_ms": 30.0,
                "total_ms": 40.0,
                "server_ms": {
                    "overview": 17.5,
                    "session": 2.0,
                    "django": 20.0,
                    "database": 10.0,
                    "dbmax": 4.0,
                    "companies": 5.0,
                    "priority": 6.0,
                    "render": 3.0,
                    "scope": 1.0,
                },
            },
        )
        self.assertNotIn("synthetic", json.dumps(metrics))

    def test_oversized_response_and_foreign_redirect_are_refused(self):
        response = SimpleNamespace(read=Mock(return_value=b"x" * (web_timing.MAX_BODY + 1)))
        browser = Mock()
        browser.open.return_value = nullcontext(response)
        with self.assertRaises(ValueError):
            web_timing.fetch(browser, "https://localhost:9441/")
        redirects = web_timing.LocalRedirect(["https://localhost:9441"])
        with self.assertRaises(ValueError):
            redirects.redirect_request(None, None, 302, None, {}, "https://attacker.example.invalid/")
