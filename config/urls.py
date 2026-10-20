from django.contrib import admin
from django.urls import include, path
from portal import sso

urlpatterns = [
    path(
        "oauth/",
        include(
            (
                [
                    path("login/<str:backend>/", sso.login, name="begin"),
                    path("complete/<str:backend>/", sso.callback, name="complete"),
                ],
                "social",
            ),
            namespace="social",
        ),
    ),
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("portal.urls")),
]
