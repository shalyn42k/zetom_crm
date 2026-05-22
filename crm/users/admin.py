from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect
from unfold.admin import ModelAdmin as UnfoldModelAdmin

from crm.users.forms import CustomUserChangeForm, CustomUserCreateForm
from crm.users.models import Role, UserProfile
from crm.users.utils import user_has_perm


class CustomUserAdmin(UnfoldModelAdmin, DjangoUserAdmin):
    add_form = CustomUserCreateForm
    form = CustomUserChangeForm

    fieldsets = (
        ("Личные данные", {"fields": ("username", "first_name", "last_name", "email", "job_title")}),
        ("Доступ", {"fields": ("role", "department", "is_active", "is_staff", "is_superuser")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "first_name",
                    "last_name",
                    "password",
                    "password_confirm",
                    "role",
                    "department",
                    "job_title",
                ),
            },
        ),
    )

    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "get_role",
        "get_department",
        "get_job_title",
        "is_staff",
    )
    list_select_related = ("profile",)

    # 🔥 ДЕЛАЕМ is_staff НЕДОСТУПНЫМ ДЛЯ ИЗМЕНЕНИЯ
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if "is_staff" in form.base_fields:
            form.base_fields["is_staff"].disabled = True  # ← выключаем редактирование
        return form

    # 🔥 ДЕЛАЕМ is_staff ВСЕГДА TRUE
    def save_model(self, request, obj, form, change):
        obj.is_staff = True  # ← принудительно включаем staff
        super().save_model(request, obj, form, change)

        profile, _ = UserProfile.objects.get_or_create(user=obj)
        if "role" in form.cleaned_data:
            profile.role = form.cleaned_data.get("role")
        if "department" in form.cleaned_data:
            department = form.cleaned_data.get("department")
            profile.department = department if department else None
        if "job_title" in form.cleaned_data:
            job_title = form.cleaned_data.get("job_title")
            profile.job_title = job_title if job_title else None
        profile.save()

    def get_role(self, obj):
        return obj.profile.role if hasattr(obj, "profile") and obj.profile.role else None
    get_role.short_description = "Роль"
    get_role.admin_order_field = "profile__role__name"

    def get_department(self, obj):
        return obj.profile.get_department_display() if hasattr(obj, "profile") else None
    get_department.short_description = "Департамент"
    get_department.admin_order_field = "profile__department"

    def get_job_title(self, obj):
        return obj.profile.job_title if hasattr(obj, "profile") else None
    get_job_title.short_description = "Должность"
    get_job_title.admin_order_field = "profile__job_title"

    def has_add_permission(self, request):
        return True

    def has_change_permission(self, request, obj=None):
        return True

    def has_delete_permission(self, request, obj=None):
        return True

    def response_post_save_change(self, request, obj):
        url = request.path
        tab = request.GET.get("tab")
        if tab:
            url += f"?tab={tab}"
        return HttpResponseRedirect(url)


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


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


@admin.register(UserProfile)
class AdminUserProfile(UnfoldModelAdmin):
    list_display = ("user", "role", "department", "job_title")
    search_fields = ("user__username", "user__email", "role__name", "department")

    def has_view_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_users")

    def has_change_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_users")

    def has_add_permission(self, request):
        return user_has_perm(request.user, "edit_users")

    def has_delete_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_users")
