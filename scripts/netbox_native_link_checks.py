"""Real NetBox ORM checks for native SSO linking; all fixtures roll back.

Run by scripts/check_netbox_native_link.py in the guarded bundled lab, or by
native_ecosystem_smoke.py in its disposable database. NATIVE_LINK_SOURCE is the
reviewed script body supplied by the test driver, never operator input.
"""

import contextlib
import io
import json
import os
import sys
import unittest
import uuid
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from social_django.models import UserSocialAuth
from tenancy.models import Tenant
from users.models import ObjectPermission
from virtualization.models import VirtualMachine

NATIVE_LINK_SOURCE = globals().get("NATIVE_LINK_SOURCE")
if not isinstance(NATIVE_LINK_SOURCE, str):
    raise RuntimeError("Run these checks through the guarded lab or disposable native driver")


class NativeLinkTests(unittest.TestCase):
    def setUp(self):
        self.atomic = transaction.atomic()
        self.atomic.__enter__()
        self.addCleanup(self.rollback)
        marker = uuid.uuid4().hex
        self.actor = get_user_model().objects.create_user(
            username="native-actor-" + marker, is_superuser=True
        )
        self.user = get_user_model().objects.create_user(
            username="native-target-" + marker, password="synthetic-kept-password"
        )
        self.tenant = Tenant.objects.create(
            name="Native link synthetic " + marker, slug="native-link-" + marker
        )
        self.permission = ObjectPermission.objects.create(
            name="Native link own tenant " + marker,
            actions=["view"],
            constraints={"tenant_id": self.tenant.pk},
        )
        self.permission.object_types.add(ContentType.objects.get_for_model(VirtualMachine))
        self.permission.users.add(self.user)
        self.subject = "synthetic-native-subject-" + marker
        self.password = self.user.password
        self.issuer = "https://native-idp.example.invalid/realms/bearings"

    def rollback(self):
        transaction.set_rollback(True)
        self.atomic.__exit__(None, None, None)

    def link(self, **overrides):
        data = {
            "actor": self.actor.username,
            "username": self.user.username,
            "subject": self.subject,
            **overrides,
        }
        with (
            patch.object(sys, "stdin", io.StringIO(json.dumps(data))),
            patch.dict(os.environ, OIDC_ISSUER=self.issuer),
        ):
            with (
                contextlib.redirect_stdout(io.StringIO()),
                patch("syslog.openlog"),
                patch("syslog.syslog") as log,
            ):
                exec(compile(NATIVE_LINK_SOURCE, "native-netbox-link", "exec"), {})
        return log

    def test_links_without_admin_app_and_preserves_roles_password_and_tenant_grants(self):
        self.assertNotIn("django.contrib.admin", settings.INSTALLED_APPS)
        log = self.link()
        binding = UserSocialAuth.objects.get(user=self.user, provider="oidc")
        event = binding.extra_data["operator_audit"]
        self.assertEqual(event["actor_id"], self.actor.pk)
        self.assertEqual(event["user_id"], self.user.pk)
        self.assertEqual(event["issuer"], self.issuer)
        self.assertEqual(event["identity"], binding.uid)
        uuid.UUID(event["event_id"])
        logged = json.loads(log.call_args.args[1])
        self.assertEqual(logged, event)
        self.assertNotIn(self.subject, json.dumps(event))
        self.user.refresh_from_db()
        self.permission.refresh_from_db()
        self.assertEqual(self.user.password, self.password)
        self.assertFalse(self.user.is_superuser)
        self.assertEqual(
            list(self.user.object_permissions.values_list("pk", flat=True)), [self.permission.pk]
        )
        self.assertEqual(self.permission.constraints, {"tenant_id": self.tenant.pk})

    def test_shared_backend_preserves_digest_namespace_without_claim_alias_migration(self):
        from django.utils.module_loading import import_string

        self.link()
        binding = UserSocialAuth.objects.get(user=self.user, provider="oidc")
        backend = import_string(settings.REMOTE_AUTH_BACKEND[0])()
        backend.id_token = {"sub": self.subject}
        with patch.object(backend, "id_token_issuer", return_value=self.issuer):
            self.assertEqual(backend.get_user_id({}, {}), binding.uid)
        self.assertEqual(backend.id_key(), "")
        self.assertIsNone(settings.SOCIAL_AUTH_OLD_ID_KEYS["oidc"])
        lookup = {"provider": "oidc", "uid": binding.uid}
        if hasattr(binding, "id_key"):
            self.assertEqual(binding.id_key, "")
            lookup["id_key"] = backend.id_key()
        self.assertEqual(UserSocialAuth.objects.get(**lookup).pk, binding.pk)
        self.assertEqual(backend.get_legacy_user_identifiers({}, {"sub": "different"}), [])
        self.assertEqual(backend.get_legacy_user_ids({}, {"id": "different"}), [])

    def test_non_admin_actor_and_inactive_target_are_refused(self):
        with self.assertRaises(get_user_model().DoesNotExist):
            self.link(actor=self.user.username)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        with self.assertRaises(get_user_model().DoesNotExist):
            self.link()
        self.assertFalse(UserSocialAuth.objects.filter(user=self.user).exists())

    def test_revoked_existing_binding_is_not_restored_or_retargeted(self):
        self.link()
        binding = UserSocialAuth.objects.get(user=self.user, provider="oidc")
        binding.extra_data["enabled"] = False
        binding.save(update_fields=["extra_data"])
        before = json.dumps(binding.extra_data, sort_keys=True)
        for subject in (self.subject, "synthetic-other-subject"):
            with self.assertRaises(ValueError):
                self.link(subject=subject)
        binding.refresh_from_db()
        self.assertEqual(json.dumps(binding.extra_data, sort_keys=True), before)
        self.assertEqual(UserSocialAuth.objects.filter(user=self.user).count(), 1)

    def test_identity_cannot_be_assigned_to_another_user(self):
        self.link()
        with self.assertRaises(ValueError):
            self.link(username=self.actor.username)
        self.assertFalse(UserSocialAuth.objects.filter(user=self.actor).exists())


result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeLinkTests))
if not result.wasSuccessful():
    raise RuntimeError("Native NetBox SSO link checks failed")
