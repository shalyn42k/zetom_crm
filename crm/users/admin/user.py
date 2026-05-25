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
from crm.users.models import Permission, UserProfile
from crm.zetom.models import DepartmentsVariants

from ._dept_actions import DepartmentActionsMixin

# claude — группировка прав по областям для вкладки Permissions.
# Порядок групп = порядок отрисовки. Порядок кодов внутри группы =
# порядок в списке внутри группы. Любые перм-коды, не попавшие сюда,
# уйдут в "Other" (см. _build_permission_groups).
PERMISSION_GROUPS = [
    (_("Dashboard"), ["view_dashboard", "view_admin_panel"]),
    (_("Users"), ["view_users", "edit_users"]),
    (_("Roles"), ["view_roles", "edit_roles"]),
    (_("Requests"), [
        "view_requests",
        "edit_requests",
        "delete_requests",
        "change_request_status",
        "assign_requests",
        "send_documents",
        "request_review",
        "resolve_review",
    ]),
    (_("Departments"), ["grant_head"]),
    (_("Logs"), ["view_logs"]),
]

# claude — заведены в БД, но реально нигде не проверяются (см. DOCS/rbac.md §7).
# Отрисуем с бейджем "Not implemented", чтобы команда не думала, что галочка
# что-то делает прямо сейчас.
STUB_PERMISSIONS = frozenset({
    "view_logs",
    "change_request_status",
    "send_documents",
    "assign_requests",
    "grant_head",
    "request_review",
    "resolve_review",
})


class CustomUserAdmin(DepartmentActionsMixin, UnfoldModelAdmin, DjangoUserAdmin):
    add_form = CustomUserCreateForm
    form = CustomUserChangeForm

    fieldsets = (
        ("Личные данные", {
            "fields": ("username", "first_name", "last_name", "email", "job_title")
        }),
        ("Доступ", {
            "fields": ("role", "is_active", "is_staff", "is_superuser")
        }),
    )

    add_fieldsets = (
        (None, {
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
        }),
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

    # is_staff нельзя менять вручную
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if "is_staff" in form.base_fields:
            form.base_fields["is_staff"].disabled = True
        return form

    # claude — контекст для tab_permissions:
    #   permission_groups — список групп {name, items[]} для отрисовки.
    #   Каждый item: {perm, from_role, extra, stub} — шаблон по этим
    #   флагам решает: locked / editable / stub.
    # Профиль/роль могут отсутствовать (nullable + ленивое создание).
    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        obj = self.get_object(request, object_id)

        if obj is not None:
            profile = getattr(obj, "profile", None)
            role = profile.role if profile else None
            role_ids = (
                set(role.permissions.values_list("id", flat=True)) if role else set()
            )
            extra_ids = (
                set(profile.extra_permissions.values_list("id", flat=True))
                if profile else set()
            )
            extra_context["permission_groups"] = self._build_permission_groups(
                role_ids, extra_ids
            )

        return super().change_view(request, object_id, form_url, extra_context)

    # claude
    @staticmethod
    def _build_permission_groups(role_ids, extra_ids):
        perms_by_code = {p.code: p for p in Permission.objects.all()}
        used = set()
        groups = []

        for group_name, codes in PERMISSION_GROUPS:
            items = []
            for code in codes:
                perm = perms_by_code.get(code)
                if perm is None:
                    continue
                used.add(code)
                items.append({
                    "perm": perm,
                    "from_role": perm.id in role_ids,
                    "extra": perm.id in extra_ids,
                    "stub": code in STUB_PERMISSIONS,
                })
            if items:
                groups.append({"name": group_name, "items": items})

        leftovers = [
            perms_by_code[code] for code in sorted(perms_by_code)
            if code not in used
        ]
        if leftovers:
            groups.append({
                "name": _("Other"),
                "items": [
                    {
                        "perm": p,
                        "from_role": p.id in role_ids,
                        "extra": p.id in extra_ids,
                        "stub": p.code in STUB_PERMISSIONS,
                    }
                    for p in leftovers
                ],
            })

        return groups

    # Логика сохранения
    def save_model(self, request, obj, form, change):
        obj.is_staff = True  # staff всегда включён
        super().save_model(request, obj, form, change)

        profile, _ = UserProfile.objects.get_or_create(user=obj)

        # claude — вкладка permissions: пишем ТОЛЬКО индивидуальные права.
        # Роль и job_title не трогаем — это другая вкладка.
        if request.GET.get("tab") == "permissions":
            selected = request.POST.getlist("extra_permissions")
            profile.extra_permissions.set(selected)
            return

        # Остальные вкладки 
        if "role" in form.cleaned_data:
            profile.role = form.cleaned_data.get("role")

        if "job_title" in form.cleaned_data:
            job_title = form.cleaned_data.get("job_title")
            profile.job_title = job_title if job_title else None

        profile.save()
        # NB: departments / main_departments умышленно НЕ трогаются здесь —
        # ими управляет вкладка Departments через HTMX-эндпоинты, иначе
        # сабмит outer-формы перезатёр бы свежие изменения вкладки. — claude

    #  Колонки в списке 
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

    # Права на действия
    def has_add_permission(self, request):
        return True

    def has_change_permission(self, request, obj=None):
        return True

    def has_delete_permission(self, request, obj=None):
        return True

    # Сохраняем вкладку при обновлении
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



#  Регистрация 
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
