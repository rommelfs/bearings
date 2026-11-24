"""Catalog selection belongs in software entry, with the same source and tenant limits."""

from pathlib import Path
import os
from unittest.mock import patch
from django.test import Client, override_settings
from django.core.exceptions import ValidationError
from .tests import Fixture
from .models import Product, ProductWatch, Installation
from .connectors.http import ConnectorError
from .product_matching import catalog_cpe, ensure_watch, suggestions

CPE = "cpe:2.3:a:misp:misp:*:*:*:*:*:*:*:*"


class InstallationCatalogTests(Fixture):
    def setUp(self):
        self.login()
        self.url_form = self.url("create-installation", pk=self.asset.pk)
        self.url_catalog = self.url("installation-catalog", pk=self.asset.pk)

    def save(self, **extra):
        return self.client.post(
            self.url_form,
            {"product_name": "MISP", "vendor": "misp", "product_key": "misp", "version": "2.5.1", **extra},
        )

    def test_misp_name_and_cpe_are_recognized_and_installation_queues_monitoring(self):
        self.assertEqual(catalog_cpe("misp", "misp"), CPE)
        self.assertEqual(catalog_cpe("unverified", "product"), "")
        self.assertEqual(suggestions(Product(name="MISP", identifier=""))[0]["vendor"], "misp")
        response = self.save()
        self.assertEqual(response.status_code, 302)
        installation = Installation.objects.get(product__name="MISP")
        self.assertEqual(
            (installation.product.identifier, installation.version, installation.asset_id),
            (CPE, "2.5.1", self.asset.pk),
        )
        watch = ProductWatch.objects.get(product=installation.product)
        self.assertEqual(
            (watch.vendor, watch.product_key, watch.enabled, watch.requested), ("misp", "misp", True, True)
        )
        self.assertFalse(installation.finding_set.exists())

    def test_direct_cpe_and_name_work_without_javascript_or_catalog_availability(self):
        for name, identifier in [("MISP", CPE), ("MISP", "")]:
            response = self.client.post(
                self.url_form, {"product_name": name, "product_identifier": identifier, "version": "2.5.2"}
            )
            self.assertEqual(response.status_code, 302)
        self.assertEqual(
            ProductWatch.objects.filter(product__name="MISP", vendor="misp", product_key="misp").count(), 2
        )

    def test_foreign_saved_products_readers_foreign_assets_and_csrf_cannot_search_or_write(self):
        foreign = Product.objects.create(organization=self.b, name="foreign-catalog-product")
        self.assertEqual(self.save(existing_product=foreign.pk).status_code, 200)
        with patch("portal.connectors.vulnerability_lookup.browse_products") as remote:
            self.assertEqual(self.client.get(self.url_catalog).status_code, 405)
            self.assertEqual(
                self.client.post(self.url("installation-catalog", pk=self.other.pk), {}).status_code, 404
            )
            self.login(self.reader)
            self.assertEqual(self.client.post(self.url_catalog, {}).status_code, 403)
            self.assertEqual(self.save().status_code, 403)
            csrf = Client(enforce_csrf_checks=True)
            csrf.force_login(self.admin)
            self.assertEqual(csrf.post(self.url_catalog, {}).status_code, 403)
            remote.assert_not_called()

    def test_search_forwards_only_public_terms_to_operator_source_and_no_software_is_created(self):
        result = {
            "results": [{"key": "misp"}],
            "total": 1,
            "page": 1,
            "pages": 1,
            "truncated": False,
            "kind": "vendors",
            "vendor": "",
        }
        with (
            override_settings(VULNERABILITY_LOOKUP_URL="https://vulnerability.example.invalid"),
            patch("portal.connectors.vulnerability_lookup.browse_products", return_value=result) as remote,
        ):
            response = self.client.post(
                self.url_catalog,
                {
                    "kind": "vendors",
                    "q": "misp",
                    "page": "1",
                    "source_url": "https://evil.example.invalid",
                    "host": "private-host",
                },
            )
        self.assertEqual(response.json(), result)
        remote.assert_called_once_with(
            "https://vulnerability.example.invalid", kind="vendors", query="misp", vendor="", page=1
        )
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(Installation.objects.count(), 1)
        with patch(
            "portal.connectors.vulnerability_lookup.browse_products",
            side_effect=ConnectorError("secret detail"),
        ):
            response = self.client.post(self.url_catalog, {"q": "misp"})
        self.assertEqual(response.status_code, 400)
        self.assertNotContains(response, "secret detail", status_code=400)

    def test_conflicting_partial_and_existing_mapping_selections_are_not_silently_applied(self):
        for extra in [
            {"product_identifier": "cpe:2.3:a:apache:log4j:*:*:*:*:*:*:*:*"},
            {"vendor": "misp", "product_key": ""},
            {"vendor": "bad/vendor"},
            {"existing_product": self.product.pk},
        ]:
            self.assertEqual(self.save(**extra).status_code, 200)
            self.assertFalse(Product.objects.filter(name="MISP").exists())
        p = Product.objects.create(organization=self.a, name="MISP", identifier=CPE)
        saved = ProductWatch.objects.create(
            product=p,
            vendor="custom",
            product_key="retained",
            source_url="https://vulnerability.circl.lu",
            enabled=False,
        )
        self.assertEqual(self.save().status_code, 200)
        saved.refresh_from_db()
        self.assertEqual((saved.vendor, saved.product_key, saved.enabled), ("custom", "retained", False))
        self.assertEqual(Installation.objects.count(), 1)
        with self.assertRaisesMessage(ValidationError, "preserved"):
            ensure_watch(p, self.admin, identity=("misp", "misp"))

    def test_paused_matching_watch_is_preserved_and_catalog_keys_need_no_lossy_cpe(self):
        p = Product.objects.create(organization=self.a, name="MISP", identifier=CPE)
        watch = ProductWatch.objects.create(
            product=p,
            vendor="misp",
            product_key="misp",
            source_url="https://vulnerability.circl.lu",
            enabled=False,
        )
        self.assertEqual(self.save().status_code, 302)
        watch.refresh_from_db()
        self.assertFalse(watch.enabled)
        self.assertEqual(catalog_cpe("vendor with spaces", "product"), "")
        self.assertEqual(
            self.save(product_name="Other", vendor="vendor with spaces", product_key="product").status_code,
            302,
        )
        other = Product.objects.get(name="Other")
        self.assertEqual(other.identifier, "")
        self.assertEqual(other.watch.vendor, "vendor with spaces")

    def test_page_has_local_and_public_choices_and_escaped_fallback_form(self):
        response = self.client.get(self.url_form)
        self.assertContains(response, "data-installation-picker")
        self.assertContains(response, 'id="id_vendor"')
        self.assertContains(response, 'id="id_product_key"')
        self.assertContains(response, "not the public CPE catalog")
        self.assertContains(response, CPE)
        self.assertContains(response, "the actual installed version")
        self.assertNotContains(response, self.other.name)
        directory = os.environ.get("BEARINGS_INSTALL_UI_DIR")
        if directory:
            Path(directory).mkdir(parents=True, exist_ok=True)
            (Path(directory) / "installation.html").write_bytes(response.content)

    def test_public_product_keys_only_get_cpes_when_independently_verified(self):
        result = {
            "results": [{"key": "misp"}, {"key": "misp-modules"}],
            "total": 2,
            "page": 1,
            "pages": 1,
            "kind": "products",
            "vendor": "misp",
        }
        with patch("portal.connectors.vulnerability_lookup.browse_products", return_value=result):
            response = self.client.post(self.url_catalog, {"kind": "products", "vendor": "misp", "q": "misp"})
        self.assertEqual(response.json()["results"][0]["identifier"], CPE)
        self.assertEqual(response.json()["results"][1]["identifier"], "")
        self.assertEqual(Installation.objects.count(), 1)
