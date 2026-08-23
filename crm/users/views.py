import base64
import secrets
from io import BytesIO
from urllib.parse import quote

import qrcode
import qrcode.image.svg
from django.contrib import messages
from django.contrib.admin.sites import site as admin_site
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views import View
from django_otp import login as otp_login
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from crm.users import otp_trust
from crm.users.models import UserProfile
from crm.users.services.deactivation import deactivate_user
from crm.users.utils import PRIVILEGED_ROLE_CODES, user_has_perm

from .forms import (
    CustomUserChangeForm, CustomUserCreateForm, UserProfileEditForm,
)


# claude — до этого КАЖДАЯ вьюшка users_ui ниже была голым `View` без
# единой проверки доступа, хотя роутится публично из config/urls.py.
# Анонимный POST на /users/<pk>/delete/ удалял любого юзера, а POST на
# /users/<pk>/edit/ с is_superuser=1 выдавал полные права — шаблон
# user_form.html рендерит форму циклом `{% for field in form %}`, то есть
# отдаёт все поля CustomUserChangeForm, включая привилегированные.
# CSRF барьером не был: токен приезжал на том же анонимном GET.
class RBACRequiredMixin(LoginRequiredMixin):
    """Логин + один permission-код из RBAC-каталога (crm/users/signals.py)."""

    required_perm = None

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not user_has_perm(
            request.user, self.required_perm
        ):
            # 403, а не редирект на логин: юзер аутентифицирован, ему просто
            # не положено — так же ведёт себя админка.
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


# claude — те же ограничения, что CustomUserAdmin.get_form ставит в админке.
# Без них users_ui оставался обходным путём вокруг всей RBAC-модели.
# Django игнорирует POST для disabled-полей (берёт значение из initial),
# поэтому это защита и от подделанной формы, а не только косметика.
def _harden_user_form(form, request, target=None):
    # is_active / is_staff из этой формы убраны совсем: staff'ом управляет
    # система, а деактивация идёт своим маршрутом (UserDeactivateView),
    # который отзывает сессии и пишет в Activity Log.
    for name in ("is_active", "is_staff"):
        form.fields.pop(name, None)

    if "is_superuser" in form.fields and not request.user.is_superuser:
        form.fields["is_superuser"].disabled = True

    role_field = form.fields.get("role")
    if role_field is not None:
        if not user_has_perm(request.user, "edit_roles"):
            role_field.disabled = True
        elif not request.user.is_superuser:
            role_field.queryset = role_field.queryset.exclude(
                code__in=PRIVILEGED_ROLE_CODES
            )
            # Себе роль не меняем — как и в админке.
            if target is not None and target.pk == request.user.pk:
                role_field.disabled = True

    return form


class UserListView(RBACRequiredMixin, View):
    """Список всех пользователей"""

    required_perm = "view_users"

    def get(self, request):
        # claude — было select_related("userprofile"), но related_name у
        # UserProfile.user — "profile", так что страница падала с FieldError
        # на каждом запросе (тесты обходили это моком менеджера).
        users = User.objects.all().select_related("profile")
        return render(request, "users/user_list.html", {"users": users})


class UserCreateView(RBACRequiredMixin, View):
    """Создание нового пользователя"""

    required_perm = "edit_users"

    def get(self, request):
        form = _harden_user_form(CustomUserCreateForm(), request)
        return render(request, "users/user_form.html", {"form": form, "mode": "create"})

    def post(self, request):
        form = _harden_user_form(CustomUserCreateForm(request.POST), request)

        if form.is_valid():
            form.save()
            messages.success(request, _("User created."))
            return redirect("user_list")

        return render(request, "users/user_form.html", {"form": form, "mode": "create"})


class UserEditView(RBACRequiredMixin, View):
    """Редактирование пользователя"""

    required_perm = "edit_users"

    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        profile = UserProfile.objects.get(user=user)

        form = _harden_user_form(
            CustomUserChangeForm(
                instance=user,
                initial={"role": profile.role, "departments": profile.departments},
            ),
            request,
            target=user,
        )

        return render(request, "users/user_form.html", {"form": form, "mode": "edit"})

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        profile = UserProfile.objects.get(user=user)

        form = _harden_user_form(
            CustomUserChangeForm(
                request.POST,
                instance=user,
                initial={"role": profile.role},
            ),
            request,
            target=user,
        )

        if form.is_valid():
            form.save()
            messages.success(request, _("User updated."))
            return redirect("user_list")

        return render(request, "users/user_form.html", {"form": form, "mode": "edit"})


# claude — раньше это был UserDeleteView с голым user.delete(). Теперь
# деактивация: единый путь с админкой (см. project-решение в
# crm/users/services/deactivation.py). Hard-delete остался только в
# админке и только суперюзеру — там есть страница подтверждения,
# которая проговаривает, что вместе с юзером умирает его Activity Log.
class UserDeactivateView(RBACRequiredMixin, View):
    """Отзыв доступа у пользователя (soft-delete)"""

    required_perm = "edit_users"

    def _guard(self, request, user):
        # Те же два правила, что в bulk-действиях админки.
        if user.pk == request.user.pk:
            return _("You cannot deactivate your own account.")
        if user.is_superuser and not request.user.is_superuser:
            return _("You don't have permission for this action.")
        return None

    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        return render(request, "users/user_confirm_delete.html", {
            "user": user,
            "blocked": self._guard(request, user),
        })

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)

        blocked = self._guard(request, user)
        if blocked:
            messages.error(request, blocked)
            return redirect("user_list")

        deactivate_user(user, actor=request.user)
        messages.success(request, _("User deactivated."))
        return redirect("user_list")


class UserDetailView(RBACRequiredMixin, View):
    """Просмотр профиля пользователя"""

    required_perm = "view_users"

    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        profile = UserProfile.objects.get(user=user)
        return render(request, "users/user_detail.html", {"user": user, "profile": profile})


# claude — своя страница профиля: отдельного permission не нужно, но
# аноним сюда попадать не должен (request.user был бы AnonymousUser,
# и форма привязалась бы к нему).
class UserProfileEditView(LoginRequiredMixin, View):
    """Редактирование своего профиля"""

    # claude — обычный render() не даёт шаблону admin/unfold-контекст
    # (is_nav_sidebar_enabled, has_permission и т.д.), поэтому сайдбар и
    # шапка молча не рендерились — страница выглядела голым HTML без стилей
    # сайта. each_context(request) — то же самое, что и обычные страницы
    # админки получают через AdminSite.
    def _context(self, request, form):
        return {**admin_site.each_context(request), "form": form}

    def get(self, request):
        form = UserProfileEditForm(instance=request.user)
        return render(request, "users/user_profile_edit.html", self._context(request, form))

    def post(self, request):
        form = UserProfileEditForm(request.POST, request.FILES, instance=request.user)

        if form.is_valid():
            form.save()
            messages.success(request, _("Profile updated."))
            return redirect("user_profile_edit")

        return render(request, "users/user_profile_edit.html", self._context(request, form))


# claude — SvgImage рисует модули как <svg:rect> с неймспейс-префиксом:
# валидно как отдельный .svg-файл, но инлайновый HTML-парсер браузера такие
# теги не узнаёт и просто не рисует (были пустые страницы). SvgPathImage
# собирает всё в один плоский <path> без префикса — рендерится инлайново.
def _qr_svg(otpauth_url: str) -> str:
    img = qrcode.make(
        otpauth_url,
        image_factory=qrcode.image.svg.SvgPathImage,
        box_size=8,
        border=2,
    )
    buf = BytesIO()
    img.save(buf)
    svg = buf.getvalue().decode()
    # claude — explicit fill: инлайновый SVG наследует стили окружающей
    # страницы; Unfold массово использует fill="none" на своих иконках,
    # а path без явного fill теоретически может отнаследовать это через
    # CSS-каскад в браузере. Явный чёрный fill убирает саму возможность.
    return svg.replace("<svg ", '<svg fill="#000000" ', 1)


def _generate_backup_codes(user, count=10):
    device, _created = StaticDevice.objects.get_or_create(
        user=user, name="backup", defaults={"confirmed": True},
    )
    device.confirmed = True
    device.save()
    device.token_set.all().delete()  # регенерация затирает старые
    codes = []
    for _ in range(count):
        code = "-".join(secrets.token_hex(2) for _ in range(2))  # "a1b2-c3d4"
        StaticToken.objects.create(device=device, token=code)
        codes.append(code)
    return codes


# claude — request.GET["next"] приходит от юзера (мы сами кладём его в
# ссылку в middleware.py, но это всё ещё GET-параметр, который любой может
# подделать в адресной строке). Без проверки — open redirect: ?next=
# https://evil.example уведёт юзера с сайта сразу после успешного 2FA.
def _safe_next(request):
    next_url = request.GET.get("next") or request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        return next_url
    return reverse("admin:index")


@login_required
def otp_gate(request):
    user = request.user
    if user.is_verified():
        return redirect(_safe_next(request))

    confirmed = TOTPDevice.objects.filter(user=user, confirmed=True).first()

    # ---------- ветка A: устройства ещё нет — регистрация ----------
    if confirmed is None:
        device, _created = TOTPDevice.objects.get_or_create(
            user=user, confirmed=False, defaults={"name": "default"},
        )
        if request.method == "POST":
            token = request.POST.get("token", "").strip()
            if device.verify_token(token):
                device.confirmed = True
                device.save()
                codes = _generate_backup_codes(user)
                otp_login(request, device)
                request.session["otp_setup_codes"] = codes  # покажем один раз
                response = redirect("otp_backup_codes")
                otp_trust.remember(request, response, user)
                return response
            messages.error(request, _("Invalid code. Please try again."))

        secret_b32 = base64.b32encode(device.bin_key).decode()
        return render(request, "users/otp_setup.html", {
            **admin_site.each_context(request),
            "qr_svg": _qr_svg(device.config_url),
            "secret": " ".join(secret_b32[i:i+4] for i in range(0, len(secret_b32), 4)),
        })

    # ---------- ветка B: устройство уже подтверждено — просто код ----------
    if request.method == "POST":
        token = request.POST.get("token", "").strip()
        matched = confirmed if confirmed.verify_token(token) else None
        if matched is None:
            static = StaticDevice.objects.filter(user=user, confirmed=True).first()
            if static and static.verify_token(token):
                matched = static
        if matched:
            otp_login(request, matched)
            response = redirect(_safe_next(request))
            otp_trust.remember(request, response, user)
            return response
        messages.error(request, _("Invalid code."))
    return render(request, "users/otp_verify.html", admin_site.each_context(request))


@login_required
def otp_backup_codes(request):
    codes = request.session.pop("otp_setup_codes", None)
    if not codes:
        # claude — повторно открыть страницу нельзя (коды одноразовые), но
        # редиректить прямиком на admin:index незачем — если юзер ещё не
        # verified, Enforce2FAMiddleware всё равно завернёт его обратно
        # следующим запросом; отправляем на otp_gate явно, а не намёком.
        return redirect("otp_gate")
    # claude — data: URI со скачиваемым файлом, без отдельной вьюхи: коды и
    # так одноразово в этом контексте, отдельный GET-эндпоинт под них не
    # завести (session-ключ уже вычитан строкой выше).
    codes_text = "Zetom CRM — 2FA backup codes\n\n" + "\n".join(codes) + "\n"
    download_href = "data:text/plain;charset=utf-8," + quote(codes_text)
    return render(request, "users/otp_backup_codes.html", {
        **admin_site.each_context(request),
        "codes": codes,
        "download_href": download_href,
    })

