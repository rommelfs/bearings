"""The bundled demo account has one company; unrelated permissions and revocations remain explicit."""

from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import override_settings
from .tests import Fixture
from .access import organizations_for
from .demo_access import scope_company_admin
from .demo_showcase import seed
from .models import InventorySource, Membership, NetBoxInstance, Organization


@override_settings(DEBUG=True)
class DemoAccessTests(Fixture):
    def setUp(self):
        self.user = get_user_model().objects.create_user("company-admin", password="local-password-only")
        self.config = {"mode": "bundled", "connections": []}
        self.orgs = []
        for i, mode in enumerate(["read_write", "read_only"]):
            org = Organization.objects.create(
                name=f"Bundled fixture {i}", slug=f"lab-fixture-{i}", operator_visibility=True
            )
            instance = NetBoxInstance.objects.create(
                name=f"Bundled {i}",
                base_url="https://netbox.bearings.test",
                token_env_var=f"NETBOX_TEST_{i}",
                access_mode=mode,
                allow_private=True,
            )
            InventorySource.objects.create(
                organization=org, mode="central", instance=instance, tenant_id=i + 1
            )
            Membership.objects.create(user=self.user, organization=org, role="admin")
            self.config["connections"].append(
                {
                    "organization_slug": org.slug,
                    "base_url": instance.base_url,
                    "token_env_var": instance.token_env_var,
                    "access_mode": mode,
                    "tenant_id": i + 1,
                }
            )
            self.orgs.append(org)
        self.env = patch.dict("os.environ", {"BEARINGS_DEV_STACK": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_retained_multicompany_fixture_is_narrowed_once_without_other_changes(self):
        dataset, _ = seed(self.platform, companies=2, assets_per_company=2)
        extras = list(Organization.objects.filter(slug__startswith="demo-explore-"))
        # Simulate the previous retained seed's broad company memberships.
        for org in extras:
            Membership.objects.get_or_create(user=self.user, organization=org, defaults={"role": "admin"})
        before_password = self.user.password
        before_circl = set(organizations_for(self.analyst).values_list("pk", flat=True))
        self.assertEqual(scope_company_admin(self.platform, self.config), 3)
        self.assertEqual(list(organizations_for(self.user).values_list("pk", flat=True)), [self.orgs[0].pk])
        self.assertEqual(scope_company_admin(self.platform, self.config), 0)
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, before_password)
        self.assertFalse(self.user.is_staff or self.user.is_superuser)
        self.assertEqual(set(organizations_for(self.analyst).values_list("pk", flat=True)), before_circl)
        seed(self.platform, companies=2, assets_per_company=2)
        self.assertEqual(Membership.objects.filter(user=self.user).count(), 1)

    def test_standalone_showcase_grants_at_most_one_and_revoked_access_is_not_restored(self):
        Membership.objects.filter(user=self.user).delete()
        seed(self.platform, companies=2, assets_per_company=2)
        self.assertEqual(Membership.objects.filter(user=self.user).count(), 1)
        Membership.objects.filter(user=self.user).delete()
        self.assertEqual(scope_company_admin(self.platform, self.config), 0)
        seed(self.platform, companies=2, assets_per_company=2)
        self.assertFalse(Membership.objects.filter(user=self.user).exists())

    def test_unrelated_or_operator_grants_fail_without_deleting_anything(self):
        Membership.objects.create(user=self.user, organization=self.a, role="admin")
        with self.assertRaises(ValidationError):
            scope_company_admin(self.platform, self.config)
        self.assertEqual(Membership.objects.filter(user=self.user).count(), 3)
        Membership.objects.filter(user=self.user, organization=self.a).delete()
        self.user.is_staff = True
        self.user.save()
        with self.assertRaises(ValidationError):
            scope_company_admin(self.platform, self.config)
        self.assertEqual(Membership.objects.filter(user=self.user).count(), 2)

    def test_external_mode_is_refused(self):
        with self.assertRaises(ValidationError):
            scope_company_admin(self.platform, {**self.config, "mode": "external"})
        self.assertEqual(Membership.objects.filter(user=self.user).count(), 2)
