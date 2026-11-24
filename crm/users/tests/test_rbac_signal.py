# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ create_rbac_defaults (crm/users/signals.py, post_migrate)
#
# Баг: Permission/Role раньше апсертились через get_or_create(defaults=...) —
# `defaults` применяется только при INSERT. Переименование текста в
# permissions_data/roles_data (например "Edit users" -> "Edit users (profile
# fields)") никогда не доходило до строк, уже существующих в БД — они
# навсегда оставались со старым именем. Поскольку старая строка больше не
# была msgid ни в одном вызове _(), {% trans %} не находил для неё перевод,
# и право отображалось сырым английским текстом независимо от языка
# интерфейса (найдено на вкладке "Uprawnienia" — edit_users/edit_roles
# показывали "Edit users"/"Edit roles" по-английски, хотя остальные права
# на той же странице были по-польски).
# ──────────────────────────────────────────────────────────────────────────────

from django.apps import apps
from django.test import TestCase

from crm.users.models import Permission, Role
from crm.users.signals import create_rbac_defaults

USERS_APP_CONFIG = apps.get_app_config("users")


class RbacDefaultsSyncExistingRowsTests(TestCase):
    def test_stale_permission_name_is_updated_on_rerun(self):
        # Simulates a Permission row created by an older version of
        # permissions_data, before its display text was renamed.
        perm = Permission.objects.get(code="edit_users")
        perm.name = "Edit users"
        perm.save()

        create_rbac_defaults(sender=USERS_APP_CONFIG)

        perm.refresh_from_db()
        self.assertEqual(perm.name, "Edit users (profile fields)")

    def test_stale_role_name_is_updated_on_rerun(self):
        role = Role.objects.get(code="specialist")
        role.name = "Spec"
        role.save()

        create_rbac_defaults(sender=USERS_APP_CONFIG)

        role.refresh_from_db()
        self.assertEqual(role.name, "Specialist")

    def test_permission_category_is_also_resynced(self):
        perm = Permission.objects.get(code="edit_users")
        perm.category = "stale_category"
        perm.save()

        create_rbac_defaults(sender=USERS_APP_CONFIG)

        perm.refresh_from_db()
        self.assertEqual(perm.category, "system")

    def test_rerun_does_not_create_duplicate_rows(self):
        before = Permission.objects.count()
        create_rbac_defaults(sender=USERS_APP_CONFIG)
        self.assertEqual(Permission.objects.count(), before)

    def test_role_permissions_still_correctly_assigned_after_rerun(self):
        create_rbac_defaults(sender=USERS_APP_CONFIG)
        admin_role = Role.objects.get(code="admin")
        self.assertTrue(
            admin_role.permissions.filter(code="edit_roles").exists()
        )
