# claude
"""Soft-delete для аккаунтов: деактивация вместо удаления.

Почему не DELETE: юзер — автор Req'ов, ассайни, аппрувер ревью, owner.
Хард-делит либо сносит каскадом половину истории, либо оставляет дыры в
записях, которые уже подписаны его именем. Плюс `LogEntry.user` — CASCADE
(модель Django, FK не поменять), то есть удаление юзера уничтожает его
аудит. Поэтому обычный путь «убрать человека из системы» — вот этот
модуль, а хард-делит оставлен суперюзеру как аварийный выход
(см. `CustomUserAdmin.has_delete_permission`).

Обе операции идемпотентны: повторный вызов ничего не делает и не пишет лог.
Роль, отделы, extra_permissions и ассайны на Req'ах не трогаются — смысл
soft-delete в том, что реактивация возвращает юзера в рабочее состояние
одним кликом.
"""
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone

from crm.users.models import TrustedDevice

# Маркеры для Activity Log. Намеренно НЕ переводятся: это данные аудита,
# а не строки интерфейса — иначе один и тот же лог хранился бы на разных
# языках в зависимости от локали того, кто нажал кнопку.
DEACTIVATED_MESSAGE = "Deactivated"
REACTIVATED_MESSAGE = "Reactivated"


def _revoke_sessions(user):
    """Завершает все живые сессии юзера. Возвращает число убитых сессий.

    Session-backend дефолтный (БД), поэтому найти сессии юзера можно только
    перебором с расшифровкой — индекса по `_auth_user_id` не существует.
    Дорого, но выполняется редко и только по кнопке админа.
    """
    target = str(user.pk)
    killed = 0
    for session in Session.objects.filter(expire_date__gte=timezone.now()).iterator():
        if session.get_decoded().get("_auth_user_id") == target:
            session.delete()
            killed += 1
    return killed


def _log(user, actor, message):
    LogEntry.objects.log_actions(
        user_id=actor.pk,
        queryset=[user],
        action_flag=CHANGE,
        change_message=message,
        single_object=True,
    )


@transaction.atomic
def deactivate_user(user, *, actor):
    """Отзывает доступ у юзера. True — если статус реально поменялся."""
    if not user.is_active:
        return False

    user.is_active = False
    # update_fields — параллельная правка профиля в другой вкладке не должна
    # перетереться сохранением всей строки.
    user.save(update_fields=["is_active"])

    # Без этого уже открытая вкладка юзера продолжила бы работать до
    # истечения session-куки.
    _revoke_sessions(user)

    # Без этого его браузер после реактивации зашёл бы вообще без 2FA.
    TrustedDevice.objects.filter(user=user).delete()

    _log(user, actor, DEACTIVATED_MESSAGE)
    return True


@transaction.atomic
def reactivate_user(user, *, actor):
    """Возвращает юзеру доступ. True — если статус реально поменялся."""
    if user.is_active:
        return False

    user.is_active = True
    user.save(update_fields=["is_active"])
    _log(user, actor, REACTIVATED_MESSAGE)
    return True
