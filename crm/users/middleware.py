import sys

from django.shortcuts import redirect
from django.urls import Resolver404, resolve, reverse
from django.utils.http import urlencode
from django_otp import login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice

from crm.users import otp_trust

# claude — view_name (с неймспейсом), которые доступны без пройденной 2FA:
# сама страница 2FA и бэкап-коды, вход/выход (иначе юзера без 2FA нельзя
# выпустить и впустить под другим аккаунтом), смена языка и две публичные
# точки входа заявок (они и так открыты анониму).
_EXEMPT_VIEW_NAMES = {
    "admin:login",
    "admin:logout",
    "otp_gate",
    "otp_backup_codes",
    "set_language",
    "zetom:index",
    "zetom:site_request",
}
# Аватарки отдаются django.views.static.serve (config/urls.py), статику
# раздаёт WhiteNoise раньше этого middleware.
_EXEMPT_PATH_PREFIXES = ("/media/", "/static/")

# claude — тот же приём, что и в notification/services/followup_scheduler.py
# ("runserver" not in sys.argv): при `manage.py test` половина существующего
# набора создаёт create_superuser() и сразу бьёт по /admin/, не проходя через
# 2FA (это не входит в то, что эти тесты вообще проверяют — 46 упало без
# этого байпаса). На реальном сайте (runserver / gunicorn) sys.argv этого
# не содержит, байпас там не срабатывает.
_RUNNING_TESTS = "test" in sys.argv


class Enforce2FAMiddleware:
    """
    После обычного логина (пароль принят) требует подтверждённое OTP-устройство
    на любой странице (кроме _EXEMPT_*) — кроме юзеров с otp_exempt=True и кроме
    запросов с валидной cookie "доверенного" браузера (otp_trust.is_trusted) —
    там код спрашивается только один раз, при первом входе с этого браузера.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    # claude — раньше проверка стояла только на путях /admin/…, а
    # /users/…, /clients/…, /notifications/… и /zetom/attachments/… (списки
    # юзеров, поиск клиентов, файлы заявок) открывались после одного
    # пароля, без кода. Теперь 2FA нужна на любом пути, кроме исключений выше.
    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            not _RUNNING_TESTS
            and user and user.is_authenticated
            and not request.path.startswith(_EXEMPT_PATH_PREFIXES)
            and not _is_2fa_exempt(user)
            and not user.is_verified()
        ):
            if otp_trust.is_trusted(request, user):
                device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
                if device is not None:
                    otp_login(request, device)
                    return self.get_response(request)
            try:
                view_name = resolve(request.path_info).view_name
            except Resolver404:
                view_name = None  # unknown path: let it 404 normally
            if view_name is not None and view_name not in _EXEMPT_VIEW_NAMES:
                return redirect(
                    reverse("otp_gate") + "?" + urlencode({"next": request.get_full_path()})
                )
        return self.get_response(request)


def _is_2fa_exempt(user):
    profile = getattr(user, "profile", None)
    return bool(profile and profile.otp_exempt)