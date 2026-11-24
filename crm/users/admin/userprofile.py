from django.contrib import admin
from unfold.admin import ModelAdmin as UnfoldModelAdmin

from crm.users.models import UserProfile
from crm.users.utils import user_has_perm


@admin.register(UserProfile)
class AdminUserProfile(UnfoldModelAdmin):
    list_display = ("user", "role", "departments", "job_title")
    search_fields = ("user__username", "user__email", "role__name")

    def has_view_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_users")

    def has_change_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_users")

    def has_add_permission(self, request):
        return user_has_perm(request.user, "edit_users")

    def has_delete_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_users")
