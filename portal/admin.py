from django.contrib import admin
from django.db import transaction
from .access import audit
from .models import (
    RTInstance,
    CompanyInstance,
    FederationGrant,
    PlumInstance,
    AuditEvent,
    InventorySource,
    Membership,
    NetBoxInstance,
    Organization,
    MOSPSource,
    FlowIntelInstance,
)


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

    def save_model(self, request, obj, form, change):
        previous = None
        if isinstance(obj, Organization) and change:
            previous = Organization.objects.get(pk=obj.pk).operator_visibility
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
        )


admin.site.register(Organization, PlatformAdmin)
admin.site.register(Membership, PlatformAdmin)


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
    list_display = ["name", "base_url", "service_org_id", "enabled"]

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
