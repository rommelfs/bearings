"""Optional customer key setup. A customer never inherits a CIRCL connection or cache."""

import uuid
from datetime import timedelta
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.core.exceptions import ValidationError
from django.db import transaction
from django.views.decorators.debug import sensitive_variables
from .access import audit, require
from .connectors.http import ConnectorError, approved_base, request_json
from .misp_credentials import encrypt, encryption_ready
from .models import MISPInstance, MISPServer, Membership, Organization, PublicRegistrationBucket


def member(actor, org):
    return actor.is_active and Membership.objects.filter(user=actor, organization=org).exists()


def permit_probe(actor):
    now = timezone.now()
    key = salted_hmac("misp-personal-key-probe", f"{actor.pk}:{int(now.timestamp()) // 600}").hexdigest()
    with transaction.atomic():
        bucket, _ = PublicRegistrationBucket.objects.get_or_create(
            key=key, defaults={"expires_at": now + timedelta(minutes=20)}
        )
        bucket = PublicRegistrationBucket.objects.select_for_update().get(pk=bucket.pk)
        if bucket.attempts >= 10:
            return False
        bucket.attempts += 1
        bucket.save(update_fields=["attempts"])
        return True


@sensitive_variables()
def connect(actor, org, server, token):
    require(member(actor, org))
    if not token or len(token) > 4096 or "\r" in token or "\n" in token:
        raise ValidationError("Enter a nonempty single-line personal read-only API key")
    if not encryption_ready():
        raise ValidationError(
            "Personal key storage requires a private application encryption secret; ask the platform operator to configure it"
        )
    current = MISPServer.objects.get(pk=server.pk)
    if not current.enabled:
        raise ValidationError("This MISP server is not approved for personal connections")
    if not permit_probe(actor):
        raise ValidationError("Too many personal MISP connection attempts. Try again in ten minutes.")
    base = approved_base(current.base_url, current.allow_private)
    identity = request_json(
        "GET",
        base + "/users/view/me",
        headers={"Authorization": token, "Accept": "application/json"},
        timeout=10,
    )
    # This response may contain auth keys. Extract one identity field only.
    user = identity.get("User", {})
    value = user.get("id") if isinstance(user, dict) else None
    if (
        isinstance(value, bool)
        or not str(value).isascii()
        or not str(value).isdigit()
        or len(str(value)) > 19
        or not 0 < int(value) < 2**63
    ):
        raise ConnectorError("MISP did not return a supported personal user identity")
    with transaction.atomic():
        Organization.objects.select_for_update().get(pk=org.pk)
        require(member(actor, org))
        approved = MISPServer.objects.select_for_update().get(pk=server.pk)
        if (
            not approved.enabled
            or approved.base_url != current.base_url
            or approved.allow_private != current.allow_private
        ):
            raise ValidationError("MISP server approval changed during setup; retry after checking its URL")
        source = (
            MISPInstance.objects.select_for_update()
            .filter(owner=actor, organization=org, server=approved, enabled=True)
            .first()
        )
        if not source:
            source = (
                MISPInstance.objects.select_for_update()
                .filter(
                    owner=actor,
                    organization=org,
                    server=approved,
                    enabled=False,
                    misp_user_id=int(value),
                    credential_kind="encrypted",
                )
                .order_by("-pk")
                .first()
            )
        if not source:
            source = MISPInstance(
                owner=actor,
                organization=org,
                server=approved,
                name="Personal MISP " + str(uuid.uuid4()),
                token_env_var="MISP_CUSTOMER_" + uuid.uuid4().hex.upper() + "_TOKEN",
            )
        if source.misp_user_id and source.misp_user_id != int(value):
            raise ValidationError(
                "This connection belongs to a different MISP user. Disconnect it first to use a different account; its cached data will not be transferred."
            )
        source.misp_user_id = int(value)
        source.base_url, source.allow_private = approved.base_url, approved.allow_private
        source.credential_kind = "encrypted"
        source.credential_ciphertext = encrypt(source, token)
        source.enabled = True
        source.last_attempt, source.last_success, source.syncing_until = None, None, None
        source.generation = uuid.uuid4()
        source.error = "Personal key connected; awaiting a complete refresh using this key"
        source.full_clean()
        source.save()
        audit(actor, org, "misp.customer_connected", source.pk)
        return source


@transaction.atomic
def disconnect(actor, source_id):
    # Same source row lock used by import publication. No other owner's source can be selected.
    context = MISPInstance.objects.only("organization_id").get(
        pk=source_id, owner=actor, organization__isnull=False
    )
    org = Organization.objects.select_for_update().get(pk=context.organization_id)
    require(actor.is_active)
    source = MISPInstance.objects.select_for_update().get(pk=source_id, owner=actor, organization=org)
    source.enabled = False
    source.credential_ciphertext = ""
    source.last_success, source.syncing_until = None, None
    source.generation = uuid.uuid4()
    source.error = "Personal connection disconnected; previous events remain unavailable"
    source.save(
        update_fields=[
            "enabled",
            "credential_ciphertext",
            "last_success",
            "syncing_until",
            "generation",
            "error",
        ]
    )
    audit(actor, source.organization, "misp.customer_disconnected", source.pk)
