from django.contrib import admin
from django.db import transaction
from django.utils import timezone
from django.urls import reverse
from django.utils.html import format_html
from .access import audit
from .models import (
    MISPInstance,
    MISPServer,
    RTInstance,
    CompanyInstance,
    FederationGrant,
    InfrastructureRegistration,
    PlumInstance,
    AuditEvent,
    InventorySource,
    Membership,
    NetBoxInstance,
    Organization,
    MOSPSource,
    FlowIntelInstance,
    UbuntuCVEStatus,
    DistroKernelRevision,
)


admin.site.site_header = "Bearings administration"
admin.site.site_title = "Bearings administration"
admin.site.index_title = "Platform administration"


class PlatformAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if self.model is Organization:
            fields += ["misp_uuid_attested_at", "misp_uuid_attested_by"]
        return fields

    def save_model(self, request, obj, form, change):
        previous_misp = None
        previous = None
        if isinstance(obj, Organization) and change:
            old_org = Organization.objects.get(pk=obj.pk)
            previous = old_org.operator_visibility
            previous_misp = old_org.misp_org_uuid
        if isinstance(obj, Organization) and obj.misp_org_uuid != previous_misp:
            obj.misp_uuid_attested_at = timezone.now() if obj.misp_org_uuid else None
            obj.misp_uuid_attested_by = request.user if obj.misp_org_uuid else None
        previous_access_mode = previous_enabled = None
        if isinstance(obj, NetBoxInstance) and change:
            old_instance = NetBoxInstance.objects.get(pk=obj.pk)
            previous_access_mode, previous_enabled = old_instance.access_mode, old_instance.enabled
        super().save_model(request, obj, form, change)
        org = obj if isinstance(obj, Organization) else getattr(obj, "organization", None)
        audit(
            request.user,
            org,
            "operator.configuration_changed",
            obj.pk,
            model=obj._meta.label,
            fields=form.changed_data,
            previous_access_mode=previous_access_mode,
            previous_enabled=previous_enabled,
            enabled=obj.enabled if isinstance(obj, NetBoxInstance) else None,
            access_mode=obj.access_mode if isinstance(obj, NetBoxInstance) else None,
            previous_visibility=previous,
            visibility=obj.operator_visibility if isinstance(obj, Organization) else None,
            previous_misp_reference=str(previous_misp) if previous_misp else None,
            misp_reference=str(obj.misp_org_uuid)
            if isinstance(obj, Organization) and obj.misp_org_uuid
            else None,
        )


class OrganizationStateFilter(admin.SimpleListFilter):
    title = "Merge status"
    parameter_name = "merge_status"

    def lookups(self, request, model_admin):
        return [("active", "Active"), ("archived", "Archived (merged)")]

    def queryset(self, request, queryset):
        if self.value() == "active":
            return queryset.filter(merged_into__isnull=True)
        if self.value() == "archived":
            return queryset.filter(merged_into__isnull=False)
        return queryset


@admin.register(Organization)
class OrganizationAdmin(PlatformAdmin):
    list_display = ["id", "name", "slug", "merge_status", "merge_destination", "operator_visibility"]
    list_display_links = ["id", "name"]
    list_filter = [OrganizationStateFilter, "operator_visibility"]
    list_select_related = ["merged_into"]
    search_fields = ["name", "slug"]
    ordering = ["name", "pk"]
    readonly_fields = ["merge_status", "merge_destination"]

    @admin.display(description="Status", ordering="merged_into_id")
    def merge_status(self, obj):
        return "Archived (merged)" if obj.merged_into_id else "Active"

    @admin.display(description="Merged into")
    def merge_destination(self, obj):
        if not obj.merged_into_id:
            return "—"
        return format_html(
            '<a href="{}">{}</a>',
            reverse("admin:portal_organization_change", args=[obj.merged_into_id]),
            obj.merged_into.display_label,
        )


@admin.register(Membership)
class MembershipAdmin(PlatformAdmin):
    list_display = ["user", "organization", "role"]
    list_select_related = ["user", "organization"]
    search_fields = [
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
        "organization__name",
    ]
    list_filter = ["role"]
    ordering = ["organization__name", "user__username", "pk"]


@admin.register(InventorySource)
class SourceAdmin(PlatformAdmin):
    list_display = [
        "organization",
        "mode",
        "instance",
        "tenant_id",
        "last_read_success",
        "last_import_success",
        "last_success",
    ]
    list_select_related = ["organization", "instance"]

    def save_model(self, request, obj, form, change):
        if not change:
            return super().save_model(request, obj, form, change)
        # The operator form can be older than an import. Never overwrite health
        # with stale readonly values, and revalidate binding identity under lock.
        with transaction.atomic():
            current = InventorySource.objects.select_for_update().get(pk=obj.pk)
            for field in form.changed_data:
                setattr(current, field, getattr(obj, field))
            current.full_clean()
            current.save(update_fields=form.changed_data)
            audit(
                request.user,
                current.organization,
                "operator.configuration_changed",
                current.pk,
                model=current._meta.label,
                fields=form.changed_data,
            )

    readonly_fields = [
        "id",
        "agent_managed",
        "agent_export_policy",
        "import_requested",
        "last_import_attempt",
        "last_import_success",
        "import_error",
        "import_summary",
        "last_read_attempt",
        "last_read_success",
        "read_error",
        "last_attempt",
        "last_success",
        "error",
    ]


@admin.register(NetBoxInstance)
class NetBoxAdmin(PlatformAdmin):
    list_display = ["name", "organization", "access_mode", "enabled", "auth_scheme"]
    list_filter = ["access_mode", "enabled"]
    search_fields = ["name"]


@admin.register(AuditEvent)
class AuditAdmin(PlatformAdmin):
    list_display = ["created_at", "organization", "actor", "action", "target"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(MOSPSource)
class MOSPAdmin(PlatformAdmin):
    list_display = ["name", "base_url", "publisher", "enabled", "last_success"]
    readonly_fields = ["last_attempt", "last_success", "error"]

    def save_model(self, request, obj, form, change):
        if not change:
            return super().save_model(request, obj, form, change)
        with transaction.atomic():
            current = MOSPSource.objects.select_for_update().get(pk=obj.pk)
            for field in form.changed_data:
                setattr(current, field, getattr(obj, field))
            current.full_clean()
            current.save(update_fields=form.changed_data)
            audit(
                request.user,
                None,
                "operator.configuration_changed",
                current.pk,
                model=current._meta.label,
                fields=form.changed_data,
            )


@admin.register(FlowIntelInstance)
class FlowIntelAdmin(PlatformAdmin):
    list_display = ["display_label", "name", "base_url", "service_org_id", "enabled"]

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            if change:
                current = FlowIntelInstance.objects.select_for_update().get(pk=obj.pk)
                for field in form.changed_data:
                    setattr(current, field, getattr(obj, field))
                current.full_clean()
                current.save(update_fields=form.changed_data)
            else:
                obj.full_clean()
                obj.save()
            audit(
                request.user,
                None,
                "operator.configuration_changed",
                obj.pk,
                model=obj._meta.label,
                fields=form.changed_data,
            )


@admin.register(RTInstance)
class RTAdmin(PlatformAdmin):
    list_display = ["name", "organization", "queue_id", "enabled", "private_queue_confirmed"]

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            if change:
                current = RTInstance.objects.select_for_update().get(pk=obj.pk)
                for field in form.changed_data:
                    setattr(current, field, getattr(obj, field))
                current.full_clean()
                current.save(update_fields=form.changed_data)
            else:
                obj.full_clean()
                obj.save()
            audit(
                request.user,
                None,
                "operator.configuration_changed",
                obj.pk,
                model=obj._meta.label,
                fields=form.changed_data,
            )


@admin.register(PlumInstance)
class PlumAdmin(RTAdmin):
    list_display = ["name", "base_url", "enabled", "fixture"]
    filter_horizontal = ["organizations"]

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            if change:
                current = PlumInstance.objects.select_for_update().get(pk=obj.pk)
                for field in form.changed_data:
                    if field != "organizations":
                        setattr(current, field, getattr(obj, field))
                current.full_clean()
                current.save()
            else:
                obj.full_clean()
                obj.save()
            audit(
                request.user,
                None,
                "operator.configuration_changed",
                obj.pk,
                model=obj._meta.label,
                fields=form.changed_data,
            )


@admin.register(CompanyInstance)
class CompanyAdmin(RTAdmin):
    list_display = ["name", "organization", "enabled", "last_success"]
    readonly_fields = ["client_id", "last_attempt", "last_success", "error"]


@admin.register(FederationGrant)
class GrantAdmin(PlatformAdmin):
    list_display = ["id", "organization", "enabled", "expires_at"]
    fields = ["organization", "publisher", "client_id", "inventory", "enabled", "expires_at"]
    readonly_fields = ["organization", "publisher", "client_id", "inventory", "expires_at"]

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        audit(request.user, obj.organization, "federation.grant_toggled", obj.pk, enabled=obj.enabled)


@admin.register(InfrastructureRegistration)
class RegistrationAdmin(PlatformAdmin):
    list_display = [
        "company_name",
        "registered_company",
        "email",
        "status",
        "email_verified_at",
        "manually_activated_at",
        "verification_delivery",
        "review_actions",
    ]
    list_filter = ["status", "verification_error"]
    search_fields = ["company_name", "email", "user__username"]
    list_select_related = ["user", "organization__merged_into"]
    fields = ["review_actions", "mail_status"] + [
        field.name for field in InfrastructureRegistration._meta.fields if field.name != "verification_digest"
    ]
    readonly_fields = fields
    actions = None

    def has_add_permission(self, request):
        return False

    @admin.display(description="Registered company")
    def registered_company(self, obj):
        return obj.organization.display_label if obj.organization_id else "No workspace yet"

    @admin.display(description="Verification email")
    def verification_delivery(self, obj):
        return (
            "Last send failed"
            if obj.verification_error
            else "No recorded send error"
            if obj.verification_attempted_at
            else "Not attempted"
        )

    @admin.display(description="Activation / review")
    def review_actions(self, obj):
        return format_html(
            '<a href="{}">Review / administrative activation / resend email →</a>',
            reverse("registration-application", args=[obj.pk]),
        )

    @admin.display(description="Service mail")
    def mail_status(self, obj):
        return format_html('<a href="{}">Service mail status & local outbox →</a>', reverse("service-mail"))


@admin.register(MISPInstance)
class MISPAdmin(PlatformAdmin):
    exclude = ["credential_ciphertext"]
    list_display = ["name", "owner", "misp_user_id", "base_url", "enabled", "last_success", "error"]
    readonly_fields = [
        "last_attempt",
        "last_success",
        "error",
        "generation",
        "syncing_until",
        "credential_nonce",
        "credential_kind",
    ]

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            if change:
                current = MISPInstance.objects.select_for_update().get(pk=obj.pk)
                for field in form.changed_data:
                    setattr(current, field, getattr(obj, field))
                current.full_clean()
                fields = list(form.changed_data)
                if set(fields) & {
                    "enabled",
                    "base_url",
                    "token_env_var",
                    "allow_private",
                    "owner",
                    "misp_user_id",
                    "organization",
                    "server",
                }:
                    import uuid

                    current.generation, current.syncing_until = uuid.uuid4(), None
                    current.last_success, current.last_attempt = None, None
                    current.error = "Awaiting a complete refresh after source policy change"
                    fields += ["generation", "syncing_until", "last_success", "last_attempt", "error"]
                    current.events.update(review_digest="")
                current.save(update_fields=fields)
            else:
                obj.full_clean()
                obj.save()
            audit(request.user, None, "misp.configuration_changed", obj.pk, fields=form.changed_data)


@admin.register(MISPServer)
class MISPServerAdmin(PlatformAdmin):
    list_display = ["name", "base_url", "enabled"]

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            if change:
                current = MISPServer.objects.select_for_update().get(pk=obj.pk)
                for field in form.changed_data:
                    setattr(current, field, getattr(obj, field))
                current.full_clean()
                current.save(update_fields=form.changed_data)
            else:
                obj.full_clean()
                obj.save()
            audit(request.user, None, "misp.server_configured", obj.pk, fields=form.changed_data)


class ReadonlyEvidenceAdmin(PlatformAdmin):
    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]


@admin.register(UbuntuCVEStatus)
class UbuntuStatusAdmin(ReadonlyEvidenceAdmin):
    list_display = ["cve", "last_attempt", "last_success", "error"]
    search_fields = ["cve"]


@admin.register(DistroKernelRevision)
class KernelEvidenceAdmin(ReadonlyEvidenceAdmin):
    list_display = ["device", "captured_at", "fingerprint"]
