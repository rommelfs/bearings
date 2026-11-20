from django.urls import reverse
from django.test import override_settings
from .tests import Fixture


class PublicSiteTests(Fixture):
    @override_settings(PUBLIC_BASE_URL="https://bearings.circl.lu")
    def test_configured_public_origin_and_head(self):
        response = self.client.get("/de/")
        self.assertContains(response, 'rel="canonical" href="https://bearings.circl.lu/de/"')
        self.assertNotContains(response, "content=noindex")
        self.assertEqual(self.client.head("/").status_code, 200)
        self.assertEqual(self.client.head("/style.css").status_code, 200)

    def test_root_is_public_marketing_with_login_signup_and_no_tenant_content(self):
        with self.assertNumQueries(0):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/accounts/login/"')
        self.assertContains(response, 'href="/register/"')
        self.assertContains(response, "NIS2")
        self.assertNotContains(response, self.asset.name)
        self.assertNotIn("sessionid", response.cookies)
        body = response.content
        self.login()
        self.assertEqual(self.client.get("/").content, body)
        self.assertEqual(reverse("overview"), "/infrastructure/")
        self.assertContains(self.client.get("/infrastructure/"), "Infrastructure overview")

    def test_all_locales_faq_assets_and_legal_link(self):
        for lang in ["en", "de", "fr", "lb"]:
            response = self.client.get("/" + lang + "/")
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "/2026/05/05/a225/jo")
            self.assertContains(response, "CSIRT")
            self.assertContains(response, 'href="/accounts/login/"')
            self.assertEqual(self.client.get("/" + lang + "/faq/").status_code, 200)
        for path in [
            "/style.css",
            "/site.js",
            "/assets/circl.svg",
            "/assets/fonts/raleway-regular.woff",
            "/assets/fonts/OFL.txt",
        ]:
            self.assertEqual(self.client.get(path).status_code, 200)
        for path in ["/assets/../copy.json", "/assets/../../config/settings.py", "/assets/missing", "/zz/"]:
            self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.get("/infrastructure/").status_code, 302)
