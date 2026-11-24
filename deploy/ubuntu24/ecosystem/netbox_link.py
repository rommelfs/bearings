"""Fixed script executed by native NetBox shell; operator inputs arrive as JSON stdin."""

import json
import os
import secrets
import sys
import syslog
import uuid
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from social_django.models import UserSocialAuth
from oidc import identity_uid

data = json.load(sys.stdin)
with transaction.atomic():
    actor = get_user_model().objects.get(username=data["actor"], is_active=True, is_superuser=True)
    user = get_user_model().objects.select_for_update().get(username=data["username"], is_active=True)
    issuer = os.environ["OIDC_ISSUER"]
    uid = identity_uid(issuer, data["subject"])
    if (
        UserSocialAuth.objects.filter(provider="oidc", uid=uid).exists()
        or user.social_auth.filter(provider="oidc").exists()
    ):
        raise ValueError("Existing binding retained; inspect/revoke it explicitly before changing identities")
    event = {
        "event": "bearings.netbox.sso_identity_linked",
        "event_id": str(uuid.uuid4()),
        "time": timezone.now().isoformat(),
        "actor_id": actor.pk,
        "actor_username": actor.username,
        "user_id": user.pk,
        "user_username": user.username,
        "issuer": issuer,
        "identity": uid,
    }
    UserSocialAuth.objects.create(
        provider="oidc",
        uid=uid,
        user=user,
        extra_data={
            "issuer": issuer,
            "subject": data["subject"],
            "enabled": True,
            "generation": secrets.token_hex(32),
            "operator_audit": event,
        },
    )
# NetBox intentionally does not install django.contrib.admin. Persist the actor
# and event atomically with the binding, then emit to the native system logger.
# Log retention is an operator concern; database metadata does not depend on it.
syslog.openlog("bearings-netbox-sso", logoption=syslog.LOG_PID, facility=syslog.LOG_AUTHPRIV)
syslog.syslog(syslog.LOG_NOTICE, json.dumps(event, sort_keys=True))
print("Explicit NetBox SSO binding created; password, tenant permissions and roles unchanged.")
