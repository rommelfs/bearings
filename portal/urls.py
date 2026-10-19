from django.urls import path
from . import views, intelligence_views

urlpatterns = [
    path("organizations/<slug:slug>/assets/<uuid:pk>/", views.asset_detail, name="asset"),
    path(
        "organizations/<slug:slug>/assets/<uuid:pk>/assessment/",
        views.edit_local_asset,
        name="edit-local-asset",
    ),
    path("organizations/<slug:slug>/intelligence/", intelligence_views.intelligence, name="intelligence"),
    path("organizations/<slug:slug>/risk-catalog/", intelligence_views.risk_catalog, name="risk-catalog"),
    path(
        "organizations/<slug:slug>/findings/<int:pk>/risk/new/",
        intelligence_views.create_risk_link,
        name="create-risk-link",
    ),
    path(
        "organizations/<slug:slug>/risk-links/<int:pk>/withdraw/",
        intelligence_views.withdraw_risk_link,
        name="withdraw-risk-link",
    ),
    path(
        "api/v1/organizations/<slug:slug>/intelligence/",
        intelligence_views.api_intelligence,
        name="api-intelligence",
    ),
    path(
        "api/v1/organizations/<slug:slug>/risk-links/<int:pk>/evidence/",
        intelligence_views.risk_link_evidence,
        name="risk-link-evidence",
    ),
    path("", views.home, name="home"),
    path("organizations/<slug:slug>/contacts/<int:pk>/edit/", views.edit_contact, name="edit-contact"),
    path(
        "api/v1/organizations/<slug:slug>/findings/<int:pk>/evidence/",
        views.api_evidence,
        name="api-evidence",
    ),
    path("contacts/verify/", views.verify_contact, name="verify-contact"),
    path("organizations/<slug:slug>/", views.detail, name="organization"),
    path("organizations/<slug:slug>/contacts/new/", views.create_contact, name="create-contact"),
    path(
        "organizations/<slug:slug>/contacts/<int:pk>/<str:action>/",
        views.contact_action,
        name="contact-action",
    ),
    path("organizations/<slug:slug>/scope/new/", views.create_claim, name="create-claim"),
    path("organizations/<slug:slug>/scope/<int:pk>/review/", views.claim_review, name="claim-review"),
    path(
        "organizations/<slug:slug>/inventory/import/",
        views.request_inventory_import,
        name="request-inventory-import",
    ),
    path(
        "organizations/<slug:slug>/assets/<uuid:pk>/missing/review/",
        views.review_missing_asset,
        name="review-missing-asset",
    ),
    path("organizations/<slug:slug>/assets/new/", views.create_asset, name="create-asset"),
    path(
        "organizations/<slug:slug>/assets/<uuid:pk>/software/new/",
        views.create_installation,
        name="create-installation",
    ),
    path(
        "organizations/<slug:slug>/software/<int:pk>/lookup/",
        views.lookup_vulnerability,
        name="lookup-vulnerability",
    ),
    path("organizations/<slug:slug>/findings/<int:pk>/review/", views.finding_review, name="finding-review"),
    path("api/v1/organizations/<slug:slug>/inventory/", views.api_inventory, name="api-inventory"),
    path("api/v1/organizations/<slug:slug>/findings/", views.api_findings, name="api-findings"),
]
