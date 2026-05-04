from django.contrib import admin
from unfold.admin import ModelAdmin

from crm.users.models import Role
from crm.users.utils import user_has_perm

from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin

admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(Role)
class AdminRole(ModelAdmin):
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


 
