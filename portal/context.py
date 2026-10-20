from django.conf import settings


def deployment(request):
    return {
        "development_environment": settings.DEBUG,
        "sso_enabled": settings.SSO_ENABLED,
        "sso_session": request.session.get("_auth_user_backend") == "config.oidc.ApprovedOpenIdConnect",
        "notification_transport": settings.NOTIFICATION_TRANSPORT,
    }
