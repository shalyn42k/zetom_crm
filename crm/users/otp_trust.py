"""«Запомнить этот браузер» для 2FA.

После реальной проверки кода (QR-настройка или обычный ввод) remember()
выдаёт долгоживущую httponly-cookie. Пока она валидна и не просрочена,
Enforce2FAMiddleware пропускает юзера без повторного запроса кода — так
2FA спрашивается только при первом входе и при заходе с нового
устройства/браузера (там просто нет нужной cookie).

В базе (TrustedDevice) хранится только SHA-256 хэш токена, не сам токен —
как со стандартными токенами сброса пароля в Django.
"""
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from crm.users.models import TrustedDevice

COOKIE_NAME = "zetom_2fa_trust"
TRUST_DAYS = 30


def _hash_token(raw_token):
    return hashlib.sha256(raw_token.encode()).hexdigest()


def is_trusted(request, user):
    """True, если cookie в запросе соответствует непросроченной записи
    TrustedDevice этого юзера. Обновляет last_used_at при успехе."""
    raw = request.COOKIES.get(COOKIE_NAME)
    if not raw or "." not in raw:
        return False
    pk_str, _, token = raw.partition(".")
    if not pk_str.isdigit():
        return False
    device = TrustedDevice.objects.filter(
        pk=int(pk_str), user=user, expires_at__gt=timezone.now(),
    ).first()
    if device is None or not secrets.compare_digest(device.token_hash, _hash_token(token)):
        return False
    device.save(update_fields=["last_used_at"])
    return True


def remember(request, response, user):
    """Выдаёт новую cookie и создаёт под неё запись TrustedDevice.
    Вызывается сразу после успешного otp_login() в otp_gate."""
    raw_token = secrets.token_urlsafe(32)
    device = TrustedDevice.objects.create(
        user=user,
        token_hash=_hash_token(raw_token),
        expires_at=timezone.now() + timedelta(days=TRUST_DAYS),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
    )
    response.set_cookie(
        COOKIE_NAME,
        f"{device.pk}.{raw_token}",
        max_age=TRUST_DAYS * 86400,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="Lax",
    )
