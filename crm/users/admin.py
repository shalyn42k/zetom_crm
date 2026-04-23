from django.contrib import admin
from unfold.admin import ModelAdmin

<<<<<<< HEAD:crm/users/admin.py
from crm.users.models import Role, UserProfile
=======
from users.models import Role, UserProfile
from users.utils import user_has_perm
>>>>>>> 39979298bd14d6dba7e63567826a8516481ff88e:users/admin.py


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
<<<<<<< HEAD:crm/users/admin.py
=======

    def has_view_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_users")

    def has_add_permission(self, request):
        return user_has_perm(request.user, "edit_users")

    def has_change_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_users")

    def has_delete_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_users")
>>>>>>> 39979298bd14d6dba7e63567826a8516481ff88e:users/admin.py
