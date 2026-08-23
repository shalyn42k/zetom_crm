"""auth.User admin override.

Class body is the team's existing CustomUserAdmin, split out of the
old single-file `admin.py` into this package. New methods added during
the Departments-tab work are marked with `# claude`; the rest is the
team's own code.
"""
from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin as UnfoldModelAdmin

from crm.notification.models import Notification
from crm.users.forms import CustomUserChangeForm, CustomUserCreateForm
from crm.users.models import Permission, Role, UserProfile
from crm.users.services.deactivation import deactivate_user, reactivate_user
from crm.users.utils import PRIVILEGED_ROLE_CODES, user_has_perm
from crm.zetom.models import DepartmentsVariants

from ._dept_actions import DepartmentActionsMixin

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
    actions = ["reset_2fa", "deactivate_users", "reactivate_users"]

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
        "get_status",
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

        # claude — снять `is_active` с самого себя = выйти из системы без
        # возможности вернуться. Дублирующий guard в `save_model`.
        if (
            obj is not None
            and obj.pk == request.user.pk
            and "is_active" in form.base_fields
        ):
            form.base_fields["is_active"].disabled = True

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

        # claude — галочка `is_active` на вкладке Permissions обязана ходить
        # через сервис деактивации (отзыв сессий + доверенных браузеров +
        # запись в Activity Log), иначе «выключенный» юзер продолжал бы
        # работать в уже открытой вкладке. Сервис идемпотентен, поэтому
        # флаг тут откатывается к значению из БД, а реальный переход
        # выполняется после super() — уже с побочными эффектами.
        wants_active = obj.is_active
        was_active = obj.is_active
        if change:
            was_active = type(obj).objects.only("is_active").get(pk=obj.pk).is_active
            # Себя деактивировать нельзя (в UI поле disabled, тут — от
            # подделанного POST).
            if obj.pk == request.user.pk:
                wants_active = was_active
            obj.is_active = was_active

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

        # claude — сам переход. Non-superuser не может выключить суперюзера —
        # то же правило, что в bulk-действиях и в has_delete_permission.
        if wants_active != was_active and not (
            obj.is_superuser and not request.user.is_superuser
        ):
            if wants_active:
                reactivate_user(obj, actor=request.user)
            else:
                deactivate_user(obj, actor=request.user)

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

    # claude — вместо колонки is_staff, которая всегда одинаковая
    # (save_model форсит её в True каждому). Реальный статус аккаунта
    # теперь несёт смысл: деактивация — основной способ убрать человека.
    @admin.display(description=_("Active"), boolean=True, ordering="is_active")
    def get_status(self, obj):
        return obj.is_active

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

    # claude — hard-delete переведён в разряд аварийного выхода и оставлен
    # только суперюзеру: обычный способ убрать человека из системы — это
    # деактивация (bulk-action «Deactivate» / галочка Active), см.
    # crm/users/services/deactivation.py. Причина в том, что удаление юзера
    # каскадом уносит его Activity Log — `LogEntry.user` это CASCADE в
    # модели самого Django, FK не поменять.
    # Себя не может удалить никто, включая суперюзера.
    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.pk == request.user.pk:
            return False
        return request.user.is_superuser

    # claude — почему это вообще понадобилось: страница удаления собирает
    # каскад и для каждой попавшей в него модели, зарегистрированной в
    # админке, дёргает её has_delete_permission. У NotificationAdmin и
    # LogEntryAdmin он жёстко False (append-only аудит), поэтому Django
    # прятал кнопку подтверждения даже у суперюзера. Обе админки остаются
    # read-only для прямого удаления — снимаем их только из каскада.
    # Цена зафиксирована в шаблоне подтверждения: инбокс и аудит
    # удаляемого юзера исчезают вместе с ним.
    # Сравниваем через str(): в perms_needed лежат lazy verbose_name,
    # прямое сравнение объектов зависело бы от активной локали.
    def get_deleted_objects(self, objs, request):
        deletable, model_count, perms_needed, protected = super().get_deleted_objects(
            objs, request
        )
        cascade_only = {
            str(Notification._meta.verbose_name),
            str(LogEntry._meta.verbose_name),
        }
        perms_needed = {p for p in perms_needed if str(p) not in cascade_only}
        return deletable, model_count, perms_needed, protected

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
            context["can_toggle_active"] = self._can_toggle_active(request, obj)
        return super().render_change_form(request, context, *args, **kwargs)

    # claude — кнопка Deactivate/Reactivate на карточке юзера.
    # Гейт один и тот же и для отрисовки кнопки, и для самого эндпоинта:
    # `edit_users` + два правила из bulk-действий (себя нельзя, чужого
    # суперюзера нельзя, если сам не суперюзер).
    @staticmethod
    def _can_toggle_active(request, obj):
        if not user_has_perm(request.user, "edit_users"):
            return False
        if obj.pk == request.user.pk:
            return False
        if obj.is_superuser and not request.user.is_superuser:
            return False
        return True

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:object_id>/toggle-active/",
                self.admin_site.admin_view(self.toggle_active_action),
                name="auth_user_toggle_active",
            ),
        ]
        return custom + urls

    # claude — кнопка живёт внутри основной формы change-view и жмётся через
    # formaction (вложенный <form> был бы невалидным HTML). Поэтому сюда
    # прилетает весь payload формы юзера — он намеренно игнорируется:
    # действие меняет только is_active, несохранённые правки полей теряются.
    def toggle_active_action(self, request, object_id):
        if request.method != "POST":
            return HttpResponseRedirect(
                reverse("admin:auth_user_change", args=[object_id])
            )

        obj = get_object_or_404(User, pk=object_id)

        if not self._can_toggle_active(request, obj):
            return HttpResponseForbidden("Permission denied")

        if obj.is_active:
            deactivate_user(obj, actor=request.user)
            self.message_user(
                request,
                _("%(name)s was deactivated and signed out.") % {"name": obj},
            )
        else:
            reactivate_user(obj, actor=request.user)
            self.message_user(
                request, _("%(name)s can log in again.") % {"name": obj},
            )

        url = reverse("admin:auth_user_change", args=[object_id])
        tab = request.GET.get("tab")
        if tab:
            url += f"?tab={tab}"
        return HttpResponseRedirect(url)

    # claude — bulk action: сброс 2FA (на случай утери телефона + backup-кодов).
    # Юзер снова встретит /users/2fa/ (регистрация) на следующем логине.
    # Заодно отзываем доверенные браузеры (TrustedDevice) — иначе старый
    # браузер продолжил бы пускать без кода уже после сброса устройства.
    @admin.action(description=_("Reset 2FA (delete OTP devices)"))
    def reset_2fa(self, request, queryset):
        if not user_has_perm(request.user, "edit_users"):
            self.message_user(request, _("No permission."), level="error")
            return
        from django_otp.plugins.otp_static.models import StaticDevice
        from django_otp.plugins.otp_totp.models import TOTPDevice

        from crm.users.models import TrustedDevice
        for u in queryset:
            TOTPDevice.objects.filter(user=u).delete()
            StaticDevice.objects.filter(user=u).delete()
            TrustedDevice.objects.filter(user=u).delete()
        self.message_user(
            request,
            _("2FA reset for %(n)s user(s). They will set it up again on next login.") % {"n": queryset.count()},
        )

    # claude — bulk soft-delete: основной способ убрать человека из системы.
    # Роль, отделы и ассайны на Req'ах сохраняются, поэтому реактивация
    # возвращает юзера в строй одним кликом.
    @admin.action(description=_("Deactivate selected users"))
    def deactivate_users(self, request, queryset):
        self._apply_activation(request, queryset, activate=False)

    @admin.action(description=_("Reactivate selected users"))
    def reactivate_users(self, request, queryset):
        self._apply_activation(request, queryset, activate=True)

    # claude — общий гейт обоих действий. Два правила те же, что стояли
    # в прежнем has_delete_permission: себя не трогаем (иначе админ
    # выключает сам себя), и non-superuser не трогает суперюзеров.
    def _apply_activation(self, request, queryset, *, activate):
        if not user_has_perm(request.user, "edit_users"):
            self.message_user(request, _("No permission."), level="error")
            return

        apply_to = reactivate_user if activate else deactivate_user
        changed = 0
        skipped = 0
        for target in queryset:
            if target.pk == request.user.pk:
                skipped += 1
                continue
            if target.is_superuser and not request.user.is_superuser:
                skipped += 1
                continue
            if apply_to(target, actor=request.user):
                changed += 1

        if activate:
            message = str(_("Reactivated %(n)s user(s).") % {"n": changed})
        else:
            message = str(
                _(
                    "Deactivated %(n)s user(s). Their sessions and trusted "
                    "browsers were revoked."
                ) % {"n": changed}
            )
        if skipped:
            message += " " + str(
                _("Skipped %(n)s (yourself or a superuser).") % {"n": skipped}
            )
        self.message_user(request, message)


#  Регистрация
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
