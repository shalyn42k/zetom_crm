from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from unfold.admin import ModelAdmin

from crm.users.models import UserProfile
from crm.users.utils import user_has_perm
from crm.zetom.models import DepartmentsVariants

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

    list_display = ("username", "email", "get_department", "is_staff", "is_active")
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
            "fields": ("username", "email", "password", "password_confirm", "role", "department"),
        }),
    )

    def get_department(self, obj):
        """Получить названиие департамента из UserProfile"""
        profile = getattr(obj, 'profile', None)
        if profile and profile.department:
            # Получаем название из DepartmentsVariants
            dept_dict = dict(DepartmentsVariants.choices)
            return dept_dict.get(profile.department, profile.department)
        return "-"
    get_department.short_description = "Департамент"

    def has_add_permission(self, request):
        return user_has_perm(request.user, "edit_users")
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        profile, _ = UserProfile.objects.get_or_create(user=obj)
        role = form.cleaned_data.get("role")
        if role is not None:
            profile.role = role

        department = form.cleaned_data.get("department")
        if department:
            profile.department = department
        elif department == "":
            profile.department = None

        profile.save()

    def has_change_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_users")

    def has_delete_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_users")


# --- UserProfile кастомизация ---
@admin.register(UserProfile)
class AdminUserProfile(ModelAdmin):
    list_display = ("user", "role", "get_department")
    show_full_result_count = False

    def get_department(self, obj):
        """Получить название департамента"""
        if obj.department:
            dept_dict = dict(DepartmentsVariants.choices)
            return dept_dict.get(obj.department, obj.department)
        return "-"
    get_department.short_description = "Департамент"

    def get_fields(self, request, obj=None):
        # Если юзер открыл СВОЙ профиль → показываем текстовые поля
        if obj and obj.user == request.user:
            return ("user_display", "role_display", "department_display")
        # Если чужой профиль → обычные поля
        return ("user", "role", "department")

    def user_display(self, obj):
        return obj.user.username
    user_display.short_description = "User"

    def role_display(self, obj):
        return obj.role.name if obj.role else "-"
    role_display.short_description = "Role"

    def department_display(self, obj):
        if obj.department:
            dept_dict = dict(DepartmentsVariants.choices)
            return dept_dict.get(obj.department, obj.department)
        return "-"
    department_display.short_description = "Department"

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
