"""
Резолвер получателей для нотификаций по Req.

Идея:
    Большинство стафф-нотификаций должно уходить главам отделов (dep_head),
    которые ведут отделы, к которым относится Req. Если по этому Req
    dep_head'ов нет (их никто не назначил или Req без отделов) — fallback
    на админов. Так система не молчит даже при кривой настройке.

Где живёт сигнал "юзер head отдела":
    UserProfile.head_of_departments — ArrayField кодов отделов
    (см. crm/users/models.py). Заполняется только admin'ом через
    HTMX-эндпоинты на странице User → Departments. Отдельно от
    main_departments, у которого совсем другая семантика ("основные
    отделы юзера", не headship).

Что отсюда отдаём:
    Базовая функция возвращает список User. Это позволяет вызывающему
    коду самому решать, что ему нужно — email (для mail-сервиса) или
    сами User-объекты (для inapp-сервиса, у которого FK на User).
    Тонкая обёртка `*_emails` фильтрует пустые/мусорные адреса.
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
    """Active users that count as administrators for notification fallback.

    Two ways to qualify: either `profile.role.code == "admin"` (the RBAC
    role from crm.users) or `is_superuser=True` (the Django flag). The
    superuser fallback covers fresh installs / dev DBs where the user from
    `createsuperuser` doesn't have an admin Role assigned yet.
    """
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
    return (
        User.objects.filter(
            is_active=True,
            profile__role__code=DEP_HEAD_ROLE_CODE,
            profile__head_of_departments__overlap=list(departments),
        )
        .select_related("profile__role")
    )


# claude
def dep_heads_or_admins(request_main):
    """Return a list of User objects to notify about `request_main`.

    Strategy:
      1. If the Req has no departments — no head can be found, fall back to admins.
      2. Otherwise — look up department_heads whose head_of_departments
         overlaps the Req's departments. If any — return them.
      3. If no head matches — fall back to admins.

    Returns a materialised list (not a QuerySet) so the caller can iterate
    twice (e.g. once to filter emails, once to set inapp recipients)
    without re-hitting the database.
    """
    departments = list(getattr(request_main, "departments", None) or [])
    if not departments:
        return list(_admins())

    heads = list(_dep_heads_for(departments))
    if heads:
        return heads
    return list(_admins())


# claude
def dep_heads_or_admins_emails(request_main):
    """Same as `dep_heads_or_admins`, but returns only non-empty emails."""
    return [u.email for u in dep_heads_or_admins(request_main) if u.email]
