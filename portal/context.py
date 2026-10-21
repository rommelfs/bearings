from .access import is_analyst
from django.conf import settings


def deployment(request):
    return {
        "development_environment": settings.DEBUG,
        "sso_enabled": settings.SSO_ENABLED,
        "sso_session": request.session.get("_auth_user_backend") == "config.oidc.ApprovedOpenIdConnect",
        "rtir_operator": request.user.is_authenticated
        and (request.user.is_superuser or is_analyst(request.user)),
        "notification_transport": settings.NOTIFICATION_TRANSPORT,
    }
