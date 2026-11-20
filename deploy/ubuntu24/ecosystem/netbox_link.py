"""Fixed script executed by native NetBox shell; operator inputs arrive as JSON stdin."""

import json
import os
import secrets
import sys
from django.contrib.admin.models import LogEntry, ADDITION
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from django.db import transaction
from social_django.models import UserSocialAuth
from oidc import identity_uid

data = json.load(sys.stdin)
with transaction.atomic():
    actor = get_user_model().objects.get(username=data["actor"], is_active=True, is_superuser=True)
    user = get_user_model().objects.get(username=data["username"], is_active=True)
    issuer = os.environ["OIDC_ISSUER"]
    uid = identity_uid(issuer, data["subject"])
    if (
        UserSocialAuth.objects.filter(provider="oidc", uid=uid).exists()
        or user.social_auth.filter(provider="oidc").exists()
    ):
        raise ValueError("Existing binding retained; inspect/revoke it explicitly before changing identities")
    binding = UserSocialAuth.objects.create(
        provider="oidc",
        uid=uid,
        user=user,
        extra_data={
            "issuer": issuer,
            "subject": data["subject"],
            "enabled": True,
            "generation": secrets.token_hex(32),
        },
    )
    LogEntry.objects.create(
        user=actor,
        content_type=ContentType.objects.get_for_model(binding),
        object_id=str(binding.pk),
        object_repr="Explicit operator SSO binding",
        action_flag=ADDITION,
        change_message="Linked an immutable issuer/subject; permissions unchanged",
    )
print("Explicit NetBox SSO binding created; password, tenant permissions and roles unchanged.")
