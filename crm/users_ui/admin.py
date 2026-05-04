from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from unfold.admin import ModelAdmin

from crm.users.models import UserProfile
from crm.users.utils import user_has_perm

# --- Django User кастомизация ---
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin

from .forms import CustomUserCreateForm, CustomUserChangeForm

# Отключаем стандартный UserAdmin
admin.site.unregister(User)

# Если UserProfile уже зарегистрирован в старом модуле — удаляем его
try:
    admin.site.unregister(UserProfile)
except NotRegistered:
    pass

# Регистрируем свой кастомный UserAdmin
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """
    Полностью кастомная админка Django User.
    """

    add_form = CustomUserCreateForm
    form = CustomUserChangeForm

    list_display = ("username", "email", "is_staff", "is_active")
    search_fields = ("username", "email")

    # Форма редактирования
    fieldsets = (
        ("Основная информация", {
            "fields": ("username", "email", "first_name", "last_name"),
        }),
        ("Статус", {
            "fields": ("is_active", "is_staff"),
        }),
    )

    # Форма создания
    add_fieldsets = (
        ("Создание пользователя", {
            "classes": ("wide",),
            "fields": ("username", "email", "password", "password_confirm", "role"),
        }),
    )

    def has_add_permission(self, request):
        return user_has_perm(request.user, "edit_users")
    
    def has_change_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_users")

    def has_delete_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_users")


# --- UserProfile кастомизация ---
@admin.register(UserProfile)
class AdminUserProfile(ModelAdmin):
    list_display = ("user", "role")
    show_full_result_count = False

    def get_fields(self, request, obj=None):
        # Если юзер открыл СВОЙ профиль → показываем текстовые поля
        if obj and obj.user == request.user:
            return ("user_display", "role_display")
        # Если чужой профиль → обычные поля
        return ("user", "role")

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
