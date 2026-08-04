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
from crm.users.models import Permission, Role, UserProfile
from crm.users.utils import user_has_perm
from crm.zetom.models import DepartmentsVariants

from ._dept_actions import DepartmentActionsMixin

# claude — роли, которые non-superuser НЕ может присвоить никому: дают
# глобальные права уровня админа, поэтому только сам superuser вправе
# повышать до них (защита от RBAC-эскалации).
PRIVILEGED_ROLE_CODES = frozenset({"admin", "all_seeing"})

# claude — группировка прав по областям для вкладки Permissions.
# Порядок групп = порядок отрисовки. Порядок кодов внутри группы =
# порядок в списке внутри группы. Любые перм-коды, не попавшие сюда,
# уйдут в "Other" (см. _build_permission_groups).
PERMISSION_GROUPS = [
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
        "manage_owners",
    ]),
    (_("Clients"), ["view_clients", "edit_clients", "delete_clients"]),
    (_("Departments"), ["grant_head"]),
    (_("Notifications"), [
        "view_inbox",
        "view_notification_log",
        "view_email_log",
    ]),
    (_("Logs"), ["view_logs"]),
]

# claude — заведены в БД, но реально нигде не проверяются (см. DOCS/rbac.md §7).
# Отрисуем с бейджем "Not implemented", чтобы команда не думала, что галочка
# что-то делает прямо сейчас. Любой код, который вышел из этого списка —
# значит уже подключён в коде.
STUB_PERMISSIONS = frozenset()
# claude — STUB-список пуст: все perm-коды в системе имеют рабочий гейт.
# Если заводишь новый код в crm/users/signals.py — не забудь
# подключить гейт в коде ИЛИ временно положить сюда, чтобы UI
# показывал «Not implemented» бейдж.


class CustomUserAdmin(DepartmentActionsMixin, UnfoldModelAdmin, DjangoUserAdmin):
    add_form = CustomUserCreateForm
    form = CustomUserChangeForm
    actions = ["reset_2fa"]

    fieldsets = (
        (_("Personal info"), {
            "fields": ("username", "first_name", "last_name", "email", "job_title")
        }),
        (_("Access"), {
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

    # claude — `is_staff` отключён всегда (управляется системой). Для
    # non-superuser ещё блокируем `is_superuser` (нельзя апгрейдить никого
    # до superuser'а) и фильтруем выбор `role` так, чтобы нельзя было
    # выдать «admin» / «all_seeing» (см. PRIVILEGED_ROLE_CODES). Если юзер
    # редактирует свой собственный профиль — role вообще disabled, чтобы
    # никто не мог даунгрейднуть/апгрейднуть себя.
    # Дополнительно: без permission `edit_roles` поле `role` целиком
    # disabled — даже если у юзера есть `edit_users` (правка профильных
    # полей), смену роли он сделать не может. Тот же permission гейтит
    # individual extras в tab_permissions.html (см. change_view ниже).
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if "is_staff" in form.base_fields:
            form.base_fields["is_staff"].disabled = True

        can_edit_roles = user_has_perm(request.user, "edit_roles")

        if "role" in form.base_fields and not can_edit_roles:
            form.base_fields["role"].disabled = True

        if not request.user.is_superuser:
            if "is_superuser" in form.base_fields:
                form.base_fields["is_superuser"].disabled = True
            if "role" in form.base_fields:
                role_field = form.base_fields["role"]
                role_field.queryset = role_field.queryset.exclude(
                    code__in=PRIVILEGED_ROLE_CODES
                )
                # Editing self: role полностью disabled — даже на не-привилегированную
                # ставить нельзя без отдельной апрувной процедуры.
                if obj is not None and obj.pk == request.user.pk:
                    role_field.disabled = True

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

        # claude — флаг для шаблона: рендерим ли individual-checkboxes как
        # editable, или как disabled-readonly. Без `edit_roles` юзер видит
        # текущее состояние, но не может его поменять.
        extra_context["can_edit_roles"] = user_has_perm(request.user, "edit_roles")

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

        # claude — defence-in-depth: даже если non-superuser обошёл UI и
        # послал POST вручную, не даём ему повысить кого-либо до superuser
        # и не даём редактировать собственную role / собственный is_superuser.
        if not request.user.is_superuser:
            # Сбрасываем is_superuser обратно к тому, что было в БД
            # (или False для нового юзера) — POST игнорируется.
            if change:
                fresh = type(obj).objects.only("is_superuser").get(pk=obj.pk)
                obj.is_superuser = fresh.is_superuser
            else:
                obj.is_superuser = False

            if change and obj.pk == request.user.pk:
                # Самому себе менять role нельзя — оставляем prior значение.
                form.cleaned_data["role"] = (
                    getattr(getattr(obj, "profile", None), "role", None)
                )

        super().save_model(request, obj, form, change)

        profile, _ = UserProfile.objects.get_or_create(user=obj)

        # claude — единый защищённый гейт на изменение role / extra_permissions.
        # Если у текущего юзера нет `edit_roles`, эти изменения молча
        # игнорируются (защита от подделанного POST), а в UI поля уже disabled
        # через `get_form` + флаг `can_edit_roles` в шаблоне.
        can_edit_roles = user_has_perm(request.user, "edit_roles")

        # claude — вкладка permissions: пишем ТОЛЬКО индивидуальные права.
        # Роль и job_title не трогаем — это другая вкладка.
        if request.GET.get("tab") == "permissions":
            if can_edit_roles:
                selected = request.POST.getlist("extra_permissions")
                profile.extra_permissions.set(selected)
            return

        # Остальные вкладки
        if "role" in form.cleaned_data and can_edit_roles:
            new_role = form.cleaned_data.get("role")
            # claude — guard: non-superuser не может присвоить privileged-role.
            if (
                new_role is not None
                and not request.user.is_superuser
                and new_role.code in PRIVILEGED_ROLE_CODES
            ):
                # Игнорируем — оставляем prior role. POST подделан / form мутирован.
                new_role = profile.role
            profile.role = new_role

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
    get_role.short_description = _("Role")
    get_role.admin_order_field = "profile__role__name"

    # claude
    def get_departments(self, obj):
        if not hasattr(obj, "profile") or not obj.profile.departments:
            return None
        labels = dict(DepartmentsVariants.choices)
        return ", ".join(str(labels.get(code, code)) for code in obj.profile.departments)
    get_departments.short_description = _("Departments")

    def get_job_title(self, obj):
        return obj.profile.job_title if hasattr(obj, "profile") else None
    get_job_title.short_description = _("Job title")
    get_job_title.admin_order_field = "profile__job_title"

    # claude — Раньше тут было `return True` безусловно: любой is_staff
    # юзер мог зайти в /admin/auth/user/<id>/ и сменить чужую роль /
    # is_superuser. Теперь гейтим через RBAC. Дополнительные safeguards
    # против эскалации — в `get_form` и `save_model` (PRIVILEGED_ROLE_CODES).
    def has_module_permission(self, request):
        return user_has_perm(request.user, "view_users")

    def has_view_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_users")

    def has_add_permission(self, request):
        return user_has_perm(request.user, "edit_users")

    def has_change_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_users")

    def has_delete_permission(self, request, obj=None):
        # claude — non-superuser не может удалить ни себя, ни superuser'а.
        if obj is not None and not request.user.is_superuser:
            if obj.pk == request.user.pk:
                return False
            if obj.is_superuser:
                return False
        return user_has_perm(request.user, "edit_users")

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

    # claude — bulk action: сброс 2FA (на случай утери телефона + backup-кодов).
    # Юзер снова встретит /users/2fa/ (регистрация) на следующем логине.
    @admin.action(description=_("Reset 2FA (delete OTP devices)"))
    def reset_2fa(self, request, queryset):
        if not user_has_perm(request.user, "edit_users"):
            self.message_user(request, _("No permission."), level="error")
            return
        from django_otp.plugins.otp_static.models import StaticDevice
        from django_otp.plugins.otp_totp.models import TOTPDevice
        for u in queryset:
            TOTPDevice.objects.filter(user=u).delete()
            StaticDevice.objects.filter(user=u).delete()
        self.message_user(
            request,
            _("2FA reset for %(n)s user(s). They will set it up again on next login.") % {"n": queryset.count()},
        )


#  Регистрация
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
