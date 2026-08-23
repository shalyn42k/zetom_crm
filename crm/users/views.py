import base64
import secrets
from io import BytesIO
from urllib.parse import quote

import qrcode
import qrcode.image.svg
from django.contrib import messages
from django.contrib.admin.sites import site as admin_site
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
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

from .forms import (
    CustomUserChangeForm, CustomUserCreateForm, UserProfileEditForm,
)


class UserListView(View):
    """Список всех пользователей"""

    def get(self, request):
        users = User.objects.all().select_related("userprofile")
        return render(request, "users/user_list.html", {"users": users})


class UserCreateView(View):
    """Создание нового пользователя"""

    def get(self, request):
        form = CustomUserCreateForm()
        return render(request, "users/user_form.html", {"form": form, "mode": "create"})

    def post(self, request):
        form = CustomUserCreateForm(request.POST)

        if form.is_valid():
            form.save()
            messages.success(request, _("User created."))
            return redirect("user_list")

        return render(request, "users/user_form.html", {"form": form, "mode": "create"})


class UserEditView(View):
    """Редактирование пользователя"""

    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        profile = UserProfile.objects.get(user=user)

        form = CustomUserChangeForm(
            instance=user,
            initial={"role": profile.role, "departments": profile.departments}
        )

        return render(request, "users/user_form.html", {"form": form, "mode": "edit"})

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        profile = UserProfile.objects.get(user=user)

        form = CustomUserChangeForm(
            request.POST,
            instance=user,
            initial={"role": profile.role}
        )

        if form.is_valid():
            form.save()
            messages.success(request, _("User updated."))
            return redirect("user_list")

        return render(request, "users/user_form.html", {"form": form, "mode": "edit"})


class UserDeleteView(View):
    """Удаление пользователя"""

    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        return render(request, "users/user_confirm_delete.html", {"user": user})

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        user.delete()
        messages.success(request, _("User deleted."))
        return redirect("user_list")


class UserDetailView(View):
    """Просмотр профиля пользователя"""

    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        profile = UserProfile.objects.get(user=user)
        return render(request, "users/user_detail.html", {"user": user, "profile": profile})


class UserProfileEditView(View):
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

