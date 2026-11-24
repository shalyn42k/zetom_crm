"""Резолвер получателей для нотификаций по RequestMain.

Каскад (см. memory/project_per_req_permissions.md):
    owners → dep_heads_of_req → admins

На первом непустом уровне останавливаемся. Идея — не спамить
вышестоящих, если ответственность уже закреплена ниже. Если owners
назначены, главные лица не получают сообщение; если owners нет, но есть
dep_head'ы отдела — admins не трогаем; если и тех нет — последний
fallback на admins, чтобы система не молчала.

Возвращаем список User-объектов (а не QuerySet) — у вызывающего кода
бывает несколько итераций (например, дернуть email и сразу зарегать
inapp-получателей), и проще иметь материализованный список.
"""
# Django imports
from django.contrib.auth import get_user_model
from django.db.models import Q

# claude
User = get_user_model()

# claude
DEP_HEAD_ROLE_CODE = "department_head"
ADMIN_ROLE_CODE = "admin"


# claude
def _admins():
    """Active users that count as administrators."""
    return (
        User.objects.filter(
            Q(is_superuser=True) | Q(profile__role__code=ADMIN_ROLE_CODE),
            is_active=True,
        )
        .select_related("profile__role")
        .distinct()
    )


# claude
def _dep_heads_for(departments):
    """Active department_head users whose head_of_departments intersects `departments`."""
    if not departments:
        return User.objects.none()
    return (
        User.objects.filter(
            is_active=True,
            profile__role__code=DEP_HEAD_ROLE_CODE,
            profile__head_of_departments__overlap=list(departments),
        )
        .select_related("profile__role")
    )


# claude
def _owners(request_main):
    """Active users marked as owners of this RequestMain.

    `send_notification_to_staff` (called from the public site form on a
    fresh RequestNull) routes through here too — RequestNull has no
    `owners` M2M, so we short-circuit to an empty list and let the
    caller fall back to dep_heads / admins.
    """
    if not hasattr(request_main, "owners"):
        return User.objects.none()
    return (
        request_main.owners.filter(is_active=True)
        .select_related("profile__role")
    )


# claude
def default_recipients(request_main):
    """Каскад owners → dep_heads_of_req → admins.

    Берём первый непустой уровень. Если ни на одном уровне нет
    активных получателей — возвращаем []. Логику «никого нет — упасть
    с ошибкой» решает вызывающий код (для inapp это критично, для
    mail-сценариев — нет).
    """
    owners = list(_owners(request_main))
    if owners:
        return owners

    departments = list(getattr(request_main, "departments", None) or [])
    heads = list(_dep_heads_for(departments)) if departments else []
    if heads:
        return heads

    return list(_admins())


# claude
def default_recipients_emails(request_main):
    """Same as `default_recipients`, but returns only non-empty emails."""
    return [u.email for u in default_recipients(request_main) if u.email]


# claude
def _all_dep_heads():
    """Все active dep_head'ы (без фильтра по отделам Req)."""
    return (
        User.objects.filter(
            is_active=True,
            profile__role__code=DEP_HEAD_ROLE_CODE,
        )
        .select_related("profile__role")
    )


# claude
def review_candidates_for(request_main, sender):
    """Полный пул кандидатов для request_review picker.

    Возвращает (default_users, extra_users):
      - default_users — то, что отправится автоматически (каскад
        owners → dep_heads_of_req → admins, фильтрованный по правилу
        «sender может слать target'у»).
      - extra_users   — остальной eligible-пул (все dep_heads + admins),
        не пересекающийся с default. Sender'а исключаем из обоих.

    Логика фильтрации `sender → target` — в
    `crm.zetom.services.per_req_perms.request_review_eligible`.
    """
    # Локальный импорт чтобы не тянуть zetom при impotr'е notification:
    from crm.zetom.services.per_req_perms import request_review_eligible

    pool_ids = set()
    pool_ids.update(_owners(request_main).values_list("id", flat=True))
    pool_ids.update(
        _dep_heads_for(request_main.departments or []).values_list("id", flat=True)
    )
    pool_ids.update(_all_dep_heads().values_list("id", flat=True))
    pool_ids.update(_admins().values_list("id", flat=True))
    pool_ids.discard(sender.pk)

    pool = list(
        User.objects.filter(pk__in=pool_ids, is_active=True)
        .select_related("profile__role")
    )
    eligible = [u for u in pool if request_review_eligible(sender, u, request_main)]
    eligible_ids = {u.pk for u in eligible}

    # Каскад с фильтром по eligible.
    owners = [u for u in _owners(request_main) if u.pk in eligible_ids]
    if owners:
        default = owners
    else:
        heads = [u for u in _dep_heads_for(request_main.departments or []) if u.pk in eligible_ids]
        if heads:
            default = heads
        else:
            default = [u for u in _admins() if u.pk in eligible_ids]

    default_ids = {u.pk for u in default}
    extras = sorted(
        (u for u in eligible if u.pk not in default_ids),
        key=lambda u: (u.username or "").lower(),
    )
    return default, extras


# claude — backward-compat aliases. Старые имена остаются, но просто
# делегируют в новые. Удалить можно после прохода по всему коду.
def dep_heads_or_admins(request_main):
    return default_recipients(request_main)


def dep_heads_or_admins_emails(request_main):
    return default_recipients_emails(request_main)
