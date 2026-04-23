from django.contrib import admin
from unfold.admin import ModelAdmin

from users.models import Role, UserProfile
from users.utils import user_has_perm


@admin.register(Role)
class AdminRole(ModelAdmin):
    list_display = ("code", "name",)

    def has_view_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_roles")

    def has_add_permission(self, request):
        return user_has_perm(request.user, "edit_roles")

    def has_change_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_roles")

    def has_delete_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_roles")


@admin.register(UserProfile)
class AdminUserProfile(ModelAdmin):
    list_display = ("user", "role")

    def has_view_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_users")

    def has_add_permission(self, request):
        return user_has_perm(request.user, "edit_users")

    def has_change_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_users")

    def has_delete_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_users")
