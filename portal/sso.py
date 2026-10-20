import time
from django.conf import settings
from django.contrib import auth, messages
from django.shortcuts import redirect
from django.http import Http404
from django.views.decorators.http import require_GET, require_POST
from social_django.models import UserSocialAuth
from social_django.views import auth as begin, complete
from config.oidc import identity_uid


@require_POST
def login(request, backend):
    if backend != "oidc":
        raise Http404
    if not settings.SSO_ENABLED:
        return redirect("login")
    return begin(request, backend="oidc")


@require_GET
def callback(request, backend):
    if backend != "oidc":
        raise Http404
    if not settings.SSO_ENABLED:
        return redirect("login")
    return complete(request, backend="oidc")


class SessionGuard:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.session.get(auth.BACKEND_SESSION_KEY) == "config.oidc.ApprovedOpenIdConnect":
            pk = request.session.get("bearings_sso_binding")
            started = request.session.get("bearings_sso_started", 0)
            binding = UserSocialAuth.objects.filter(pk=pk, user_id=request.user.pk, provider="oidc").first()
            try:
                valid = (
                    settings.SSO_ENABLED
                    and request.user.is_active
                    and binding
                    and binding.extra_data.get("enabled", False)
                    and binding.extra_data.get("generation") == request.session.get("bearings_sso_generation")
                    and 0 <= time.time() - started < settings.SSO_SESSION_SECONDS
                    and binding.uid
                    == identity_uid(settings.SSO_ISSUER, binding.extra_data.get("subject", ""))
                )
            except (TypeError, ValueError):
                valid = False
            if not valid:
                auth.logout(request)
        return self.get_response(request)

    def process_exception(self, request, exception):
        if request.path.startswith("/oauth/") and not isinstance(exception, Http404):
            # Do not echo provider text, codes, tokens or upstream URLs into pages/logs.
            messages.error(
                request,
                "SSO sign-in failed or this identity is not approved. Local sign-in remains available.",
            )
            return redirect("login")
        return None
