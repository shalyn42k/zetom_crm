from django.contrib import admin
from unfold.admin import ModelAdmin

from crm.users.models import Role, UserProfile
from crm.users.utils import user_has_perm


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


@admin.register(UserProfile)
class AdminUserProfile(ModelAdmin):
    list_display = ("user", "role")
    show_full_result_count = False

    # -----------------------------
    #  КЛЮЧЕВОЙ МЕТОД
    # -----------------------------
    def get_fields(self, request, obj=None):
        # Если юзер открыл СВОЙ профиль → показываем текстовые поля
        if obj and obj.user == request.user:
            return ("user_display", "role_display")
        # Если чужой профиль → обычные поля
        return ("user", "role")

    # Текстовые поля (НЕ ForeignKey → нет ссылок)
    def user_display(self, obj):
        return obj.user.username
    user_display.short_description = "User"

    def role_display(self, obj):
        return obj.role.name if obj.role else "-"
    role_display.short_description = "Role"

    # Права
    def has_view_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_users")

    def has_add_permission(self, request):
        return user_has_perm(request.user, "edit_users")

    def has_change_permission(self, request, obj=None):
        if obj and obj.user == request.user:
            return False
        return user_has_perm(request.user, "edit_users")

    def has_delete_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_users")
