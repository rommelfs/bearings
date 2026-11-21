"""Explicit association of an approved constituent's own local and OIDC identities."""

import time
import uuid
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import salted_hmac
from datetime import timedelta
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods
from config.oidc import AuthForbidden
from social_django.models import UserSocialAuth
from .access import audit, require, is_analyst
from .circl_views import private_response
from .models import InfrastructureRegistration, PublicRegistrationBucket
from .sso import login as begin_login

INTENT = "bearings_sso_onboarding"


def eligible_registration(user):
    if not user.is_active or user.is_staff or user.is_superuser or is_analyst(user):
        return None
    return (
        InfrastructureRegistration.objects.filter(
            user=user,
            status="approved",
            organization__operator_visibility=True,
            organization__membership__user=user,
            organization__membership__role="admin",
        )
        .select_related("organization")
        .first()
    )


def permit_link_attempt(user):
    now = timezone.now()
    window = int(now.timestamp()) // 600
    key = salted_hmac("constituent-sso-reauth", f"{user.pk}|{window}").hexdigest()
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


class LinkSSOForm(forms.Form):
    password = forms.CharField(
        label="Your current local Bearings password",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    checked = forms.BooleanField(
        label="Link only an SSO identity I control to my approved company account. My company membership and application permissions stay unchanged."
    )


@login_required
@never_cache
@sensitive_post_parameters()
@require_http_methods(["GET", "POST"])
def settings_view(request):
    item = eligible_registration(request.user)
    bindings = UserSocialAuth.objects.filter(user=request.user, provider="oidc")
    form = LinkSSOForm(request.POST if request.method == "POST" else None)
    allowed = bool(settings.SSO_ENABLED and item and not bindings.exists())
    if request.method == "POST":
        require(allowed)
        if not permit_link_attempt(request.user):
            form.add_error(
                None,
                "Too many identity-link attempts. Try again in ten minutes or contact the platform operator.",
            )
        elif form.is_valid():
            if request.session.get(
                "_auth_user_backend"
            ) != "django.contrib.auth.backends.ModelBackend" or not request.user.check_password(
                form.cleaned_data["password"]
            ):
                form.add_error(
                    "password", "Sign in locally and confirm your current local password before linking."
                )
            else:
                request.session[INTENT] = {
                    "user": request.user.pk,
                    "registration": str(item.pk),
                    "expires": time.time() + 300,
                }
                # Use the regular POST/CSRF/PKCE/nonce path; never accept a client issuer/subject.
                old = request.POST
                from django.http import QueryDict

                request.POST = QueryDict(mutable=True)
                request.POST["next"] = reverse("sso-settings")
                try:
                    return begin_login(request, "oidc")
                finally:
                    request.POST = old
    return private_response(
        render(
            request,
            "portal/sso_settings.html",
            {
                "registration": item,
                "bindings": bindings,
                "form": form if allowed else None,
                "sso_enabled": settings.SSO_ENABLED,
            },
        )
    )


def link_verified_identity(backend, uid, user=None, social=None, response=None, **kwargs):
    """Called only after signed OIDC verification and social-user collision checks."""
    if not backend.setting("CONSTITUENT_ONBOARDING", False):
        return None
    intent = backend.strategy.session_get(INTENT)
    if not intent:
        return None
    backend.strategy.session_set(INTENT, None)
    try:
        if not user or intent["user"] != user.pk or not 0 < intent["expires"] - time.time() <= 300:
            raise ValueError()
        issuer = backend.id_token_issuer()
        from config.oidc import identity_uid

        subject = response.get("sub")
        if issuer != settings.SSO_ISSUER or identity_uid(issuer, subject) != uid:
            raise ValueError()
        with transaction.atomic():
            locked = get_user_model().objects.select_for_update().get(pk=user.pk)
            item = eligible_registration(locked)
            if (
                not item
                or str(item.pk) != intent["registration"]
                or social
                or UserSocialAuth.objects.filter(user=locked, provider="oidc").exists()
            ):
                raise ValueError()
            binding = UserSocialAuth.objects.create(
                user=locked,
                provider="oidc",
                uid=uid,
                extra_data={
                    "issuer": issuer,
                    "subject": subject,
                    "enabled": True,
                    "generation": str(uuid.uuid4()),
                    "last_verified": 0,
                    "onboarding_registration": str(item.pk),
                },
            )
            audit(locked, item.organization, "sso.constituent_identity_linked", locked.pk, identity=uid)
            return {"social": binding, "user": locked, "new_association": True}
    except (ValueError, KeyError, TypeError, IntegrityError, ValidationError):
        raise AuthForbidden(backend) from None
