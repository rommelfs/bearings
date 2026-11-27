from django.template import Context, Template
from django.test import SimpleTestCase


class CveLookupTests(SimpleTestCase):
    def test_fixed_destination_and_no_cross_site_context(self):
        template = Template("{% load ui_cve %}{% cve_lookup identifier %}")
        rendered = template.render(Context({"identifier": "cVe-2026-124741"}))
        self.assertIn('href="https://vulnerability.circl.lu/vuln/cve-2026-124741"', rendered)
        self.assertIn('target="_blank" rel="noopener noreferrer"', rendered)
        self.assertIn('aria-label="Open CVE-2026-124741 in CIRCL Vulnerability-Lookup (new tab)"', rendered)
        for unsafe in ("GHSA-test", "CVE-2026-124741?organization=private", "javascript:foo", "", None):
            with self.subTest(unsafe=unsafe):
                self.assertEqual(template.render(Context({"identifier": unsafe})), "")
