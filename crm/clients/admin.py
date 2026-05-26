from django.contrib import admin

from crm.users.utils import user_has_perm

from .models import Client


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "company_name", "email", "phone")
    search_fields = ("first_name", "last_name", "company_name", "email", "phone")

    # claude — раньше тут не было гейтов: любой is_staff видел и менял
    # базу клиентов. Привязываем к RBAC-кодам view_clients / edit_clients
    # (см. crm/users/signals.py). superuser получает всё через user_has_perm.
    def has_module_permission(self, request):
        return user_has_perm(request.user, "view_clients")

    def has_view_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_clients")

    def has_add_permission(self, request):
        return user_has_perm(request.user, "edit_clients")

    def has_change_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_clients")

    def has_delete_permission(self, request, obj=None):
        return user_has_perm(request.user, "delete_clients")