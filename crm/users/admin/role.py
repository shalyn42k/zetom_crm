from django.contrib import admin
from unfold.admin import ModelAdmin as UnfoldModelAdmin

from crm.users.models import Role
from crm.users.utils import user_has_perm


@admin.register(Role)
class AdminRole(UnfoldModelAdmin):
    list_display = ("code", "name")

    def has_view_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_roles")

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_list_display_links(self, request, list_display):
        return None
