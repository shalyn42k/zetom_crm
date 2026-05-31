from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission as DjangoPermission
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_migrate
from django.dispatch import receiver

from crm.users.models import Permission, Role

User = get_user_model()

print("RBAC SIGNALS LOADED")


@receiver(post_migrate)
def create_rbac_defaults(sender, **kwargs):
    # Запускаем только для приложения crm.users
    if sender.name != "crm.users":
        return

    print("RBAC SIGNAL RUNNING FOR USERS")

    # Проверяем, что таблицы существуют
    try:
        Permission.objects.exists()
        Role.objects.exists()
        User.objects.exists()
    except Exception:
        print("RBAC: tables are not created yet — skipping")
        return

    # claude — permission-каталог. Каждый код должен иметь гейт в коде;
    # «мёртвые» коды помечены * рядом со статусом в DOCS/rbac.md.
    # Расширения (manage_owners / view_inbox / view_*_log) — для notification
    # и per-Req owner-флоу; их гейты см. в crm/notification/views.py,
    # crm/notification/admin.py, crm/zetom/services/per_req_perms.py.
    permissions_data = [
        ("view_users", "View users"),
        ("edit_users", "Edit users (profile fields)"),
        ("view_roles", "View roles"),
        ("edit_roles", "Assign role and individual permissions to users"),
        ("view_requests", "View requests"),
        ("edit_requests", "Edit requests"),
        ("delete_requests", "Delete requests"),
        ("view_logs", "View logs"),
        ("change_request_status", "Change request status"),
        ("send_documents", "Send document emails (oferta/zlecenie/wniosek)"),
        ("assign_requests", "Assign/unassign users to requests"),
        ("grant_head", "Grant/revoke department head"),
        ("request_review", "Request review from a higher role"),
        ("resolve_review", "Resolve review (approve/reject)"),
        # claude — per-Req owners (см. memory project_per_req_permissions.md).
        # Контекстный fallback admin/dep_head-of-Req сохраняется в коде;
        # этот perm позволяет ДЕЛЕГИРОВАТЬ право через extra_permissions.
        ("manage_owners", "Set/unset owner on a request"),
        # claude — gates для inapp-канала и админ-логов.
        ("view_inbox", "Open the in-app notifications inbox"),
        ("view_notification_log", "View the in-app notification audit log (admin)"),
        ("view_email_log", "View the email notification audit log (admin)"),
        # claude — clients module gates. Раньше ClientAdmin + search/autofill
        # views были без проверок; любой staff (а search вообще аноним) мог
        # выгрузить базу клиентов.
        ("view_clients", "View clients"),
        ("edit_clients", "Edit/create clients"),
        ("delete_clients", "Delete clients"),
    ]

    # Создание permissions
    perm_objects = {}
    for code, name in permissions_data:
        perm, _ = Permission.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "category": "system",  # claude — обязательная категория для UI-группировки
            }
        )
        perm_objects[code] = perm

    # claude — чистим Permission-записи, которые ушли из permissions_data
    # (например, удалённые декоративные view_dashboard / view_admin_panel).
    # Иначе они продолжают висеть в БД мёртвым грузом, появляются в админ-UI
    # как доступные для extra_permissions и путают команду.
    valid_codes = {code for code, _ in permissions_data}
    Permission.objects.exclude(code__in=valid_codes).delete()

    # claude — наборы по матрице DOCS/rbac.md §5.
    # all_seeing по дизайну пустая роль-шаблон, права раздаются индивидуально
    # через extra_permissions.
    roles_data = {
        "admin": {
            "name": "Administrator",
            "perms": [p[0] for p in permissions_data],
        },
        "department_head": {
            "name": "Department Head",
            "perms": [
                "view_users",
                "view_requests",
                "edit_requests",
                "delete_requests",
                "view_logs",
                "change_request_status",
                "send_documents",
                "assign_requests",
                "resolve_review",
                # claude — dep_head управляет owner-флагом на «своих» Req'ах
                # (контекст dep_head-of-Req проверяется отдельно в коде).
                "manage_owners",
                "view_inbox",
                # claude — dep_head создаёт Req'ы и видит клиентов в форме.
                "view_clients",
                "edit_clients",
            ],
        },
        "specialist": {
            "name": "Specialist",
            "perms": [
                "view_requests",
                "edit_requests",
                "send_documents",
                "assign_requests",
                "request_review",
                "view_inbox",
                # claude — spec'у нужен autofill и search клиентов в форме Req.
                "view_clients",
                "edit_clients",
            ],
        },
        "auditor": {
            "name": "Auditor",
            "perms": [
                "view_users",
                "view_roles",
                "view_requests",
                "view_logs",
                # claude — read-only аудит логов уведомлений.
                "view_inbox",
                "view_notification_log",
                "view_email_log",
                "view_clients",
            ],
        },
        "all_seeing": {
            "name": "All Seeing",
            "perms": [],
        },
    }

    # Создание ролей
    for code, data in roles_data.items():
        role, _ = Role.objects.get_or_create(
            code=code,
            defaults={"name": data["name"]}
        )
        role.permissions.set([perm_objects[p] for p in data["perms"]])

    # claude — старый общий Role(code=custom) больше не используется.
    # Индивидуальные права теперь живут в UserProfile.extra_permissions.
    # Чистим, чтобы не висел осиротевший ряд (юзеров с этой ролью
    # отвязываем на NULL — есть on_delete=SET_NULL).
    Role.objects.filter(code="custom").delete()

    # Map custom permissions → Django permissions
    django_perm_map = {
        "view_requests": ("zetom", "requestmain"),
        "edit_requests": ("zetom", "requestmain"),
        "delete_requests": ("zetom", "requestmain"),

        "view_users": ("users", "userprofile"),
        "edit_users": ("users", "userprofile"),

        "view_roles": ("users", "role"),
        "edit_roles": ("users", "role"),
    }

    # 4. Assign Django permissions to users based on roles
    for user in User.objects.all():
        profile = getattr(user, "profile", None)
        if not profile or not profile.role:
            continue

        if user.is_superuser:
            continue

        role = profile.role

        for perm_code in role.permissions.values_list("code", flat=True):
            if perm_code not in django_perm_map:
                continue

            app_label, model_name = django_perm_map[perm_code]

            try:
                ct = ContentType.objects.get(app_label=app_label, model=model_name)
            except ContentType.DoesNotExist:
                print(f"WARNING: ContentType not found for {app_label}.{model_name}")
                continue

            perms = DjangoPermission.objects.filter(content_type=ct)
            user.user_permissions.add(*perms)

    print("RBAC DEFAULT ROLES & PERMISSIONS CREATED")
