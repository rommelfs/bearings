from .access import is_analyst
from django.conf import settings


def deployment(request):
    from .models import DemoDataset
    from .navigation import workspace
    from .workspace_views import remembered_company, view_switch

    selected = remembered_company(request)
    operator = (
        request.user.is_authenticated
        and request.user.is_active
        and (request.user.is_superuser or is_analyst(request.user))
    )

    showcase = request.user.is_authenticated and DemoDataset.objects.filter(state="active").exists()
    switch = view_switch(request, selected, operator)
    return {
        **workspace(
            request,
            show_examples=showcase,
            company=switch.get("navigation_company"),
            national=switch.get("workspace_national", False),
        ),
        "selected_company_workspace": selected,
        **switch,
        "synthetic_showcase_active": showcase,
        "development_environment": settings.DEBUG,
        "sso_enabled": settings.SSO_ENABLED,
        "sso_session": request.session.get("_auth_user_backend") == "config.oidc.ApprovedOpenIdConnect",
        "rtir_operator": operator,
        "notification_transport": settings.NOTIFICATION_TRANSPORT,
    }
