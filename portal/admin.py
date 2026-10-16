from django.contrib import admin
from .access import audit
from .models import AuditEvent, InventorySource, Membership, Organization


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
        super().save_model(request, obj, form, change)
        org = obj if isinstance(obj, Organization) else getattr(obj, "organization", None)
        audit(
            request.user,
            org,
            "operator.configuration_changed",
            obj.pk,
            model=obj._meta.label,
            previous_visibility=previous,
            visibility=obj.operator_visibility if isinstance(obj, Organization) else None,
        )


admin.site.register(Organization, PlatformAdmin)
admin.site.register(Membership, PlatformAdmin)
admin.site.register(InventorySource, PlatformAdmin)


@admin.register(AuditEvent)
class AuditAdmin(PlatformAdmin):
    list_display = ["created_at", "organization", "actor", "action", "target"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
