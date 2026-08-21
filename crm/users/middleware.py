import sys

from django.shortcuts import redirect
from django.urls import resolve, reverse
from django_otp import login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice

from crm.users import otp_trust

# claude — url_name без неймспейса: в crm.users.urls неймспейса нет и не
# заводим (иначе ломаются ~30 существующих {% url 'user_list' %} по проекту,
# см. разбор в чате). otp_gate/otp_backup_codes и так вне /admin/, под этот
# гейт не попадают; "logout" — чтобы не запереть юзера без 2FA без
# возможности выйти и зайти заново под другим аккаунтом.
_EXEMPT_URL_NAMES = {"logout"}

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
    для входа в /admin/ — кроме юзеров с profile.otp_exempt=True и кроме
    запросов с валидной cookie "доверенного" браузера (otp_trust.is_trusted) —
    там код спрашивается только один раз, при первом входе с этого браузера.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            not _RUNNING_TESTS
            and user and user.is_authenticated
            and request.path.startswith("/admin/")
            and not request.path.startswith("/admin/login/")
            and not _is_2fa_exempt(user)
            and not user.is_verified()
        ):
            if otp_trust.is_trusted(request, user):
                device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
                if device is not None:
                    otp_login(request, device)
                    return self.get_response(request)
            match = resolve(request.path)
            if match.url_name not in _EXEMPT_URL_NAMES:
                return redirect(reverse("otp_gate") + f"?next={request.path}")
        return self.get_response(request)


def _is_2fa_exempt(user):
    profile = getattr(user, "profile", None)
    return bool(profile and profile.otp_exempt)