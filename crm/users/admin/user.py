"""auth.User admin override.

Class body is the team's existing CustomUserAdmin, split out of the
old single-file `admin.py` into this package. New methods added during
the Departments-tab work are marked with `# claude`; the rest is the
team's own code.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin as UnfoldModelAdmin

from crm.users.forms import CustomUserChangeForm, CustomUserCreateForm
from crm.users.models import UserProfile
from crm.zetom.models import DepartmentsVariants

from ._dept_actions import DepartmentActionsMixin


class CustomUserAdmin(DepartmentActionsMixin, UnfoldModelAdmin, DjangoUserAdmin):
    add_form = CustomUserCreateForm
    form = CustomUserChangeForm

    fieldsets = (
        ("Личные данные", {"fields": ("username", "first_name", "last_name", "email", "job_title")}),
        ("Доступ", {"fields": ("role", "is_active", "is_staff", "is_superuser")}),
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
                    "departments",
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
        "get_departments",
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

        profile, _created = UserProfile.objects.get_or_create(user=obj)
        if "role" in form.cleaned_data:
            profile.role = form.cleaned_data.get("role")
        if "job_title" in form.cleaned_data:
            job_title = form.cleaned_data.get("job_title")
            profile.job_title = job_title if job_title else None
        profile.save()
        # NB: departments / main_departments умышленно НЕ трогаются здесь —
        # ими управляет вкладка Departments через HTMX-эндпоинты, иначе
        # сабмит outer-формы перезатёр бы свежие изменения вкладки. — claude

    def get_role(self, obj):
        return obj.profile.role if hasattr(obj, "profile") and obj.profile.role else None
    get_role.short_description = "Роль"
    get_role.admin_order_field = "profile__role__name"

    # claude
    def get_departments(self, obj):
        if not hasattr(obj, "profile") or not obj.profile.departments:
            return None
        labels = dict(DepartmentsVariants.choices)
        return ", ".join(labels.get(code, code) for code in obj.profile.departments)
    get_departments.short_description = _("Departments")

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

    # claude — впрыскиваем контекст для Departments-вкладки на первый GET,
    # чтобы партиал отрисовался без JS.
    def render_change_form(self, request, context, *args, **kwargs):
        obj = context.get("original")
        if obj is not None:
            context.update(self._build_dept_context(request, obj))
        return super().render_change_form(request, context, *args, **kwargs)


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
