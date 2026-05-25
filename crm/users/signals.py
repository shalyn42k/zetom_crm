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
    # Run only for crm.users app
    if sender.name != "crm.users":
        return

    print("RBAC SIGNAL RUNNING FOR USERS")

    # Ensure tables exist
    try:
        Permission.objects.exists()
        Role.objects.exists()
        User.objects.exists()
    except Exception:
        print("RBAC: tables are not created yet — skipping")
        return

    # claude — расширил permissions_data по матрице DOCS/rbac.md §5.
    # Новые коды (view_logs ... resolve_review) пока НИГДЕ не проверяются —
    # они заведены как заглушки, видны в админ-вкладке Permissions, чтобы
    # команда могла раздавать их заранее. Гейты по этим pерм-кодам подключим
    # отдельным куском (см. план в DOCS/rbac.md §7.2).
    permissions_data = [
        ("view_dashboard", "View dashboard"),
        ("view_admin_panel", "View admin panel"),
        ("view_users", "View users"),
        ("edit_users", "Edit users"),
        ("view_roles", "View roles"),
        ("edit_roles", "Edit roles"),
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
    ]

    perm_objects = {}
    for code, name in permissions_data:
        perm, _ = Permission.objects.get_or_create(
            code=code,
            defaults={"name": name}
        )
        perm_objects[code] = perm

    # claude — наборы по матрице DOCS/rbac.md §5. all_seeing по дизайну
    # пустая роль-шаблон, права раздаются индивидуально через extra_permissions.
    roles_data = {
        "admin": {
            "name": "Administrator",
            "perms": [p[0] for p in permissions_data],
        },
        "department_head": {
            "name": "Department Head",
            "perms": [
                "view_dashboard",
                "view_users",
                "view_requests",
                "edit_requests",
                "delete_requests",
                "view_logs",
                "change_request_status",
                "send_documents",
                "assign_requests",
                "resolve_review",
            ],
        },
        "specialist": {
            "name": "Specialist",
            "perms": [
                "view_dashboard",
                "view_requests",
                "edit_requests",
                "send_documents",
                "assign_requests",
                "request_review",
            ],
        },
        "auditor": {
            "name": "Auditor",
            "perms": [
                "view_dashboard",
                "view_admin_panel",
                "view_users",
                "view_roles",
                "view_requests",
                "view_logs",
            ],
        },
        "all_seeing": {
            "name": "All Seeing",
            "perms": [],
        },
    }

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
