# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ МОДЕЛЕЙ users
#
# Что тут тестируется:
#   • Permission — поля сохраняются, __str__ возвращает name
#   • Role — поля, M2M к Permission, __str__
#   • UserProfile — поля по умолчанию (пустые ArrayField'ы), is_role(),
#     clean() (инварианты подмножеств), departments_summary()
#
# Паттерн: objects.create() → refresh_from_db() — перечитываем из БД,
# чтобы не тестировать Python-объект в памяти.
# ──────────────────────────────────────────────────────────────────────────────

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from crm.users.models import Permission, Role, UserProfile

User = get_user_model()

# ─────────────────────────── Permission ───────────────────────────────────────


class PermissionModelTests(TestCase):
    """Permission — простая модель с code (unique) и name.

    Используем коды с префиксом test__ чтобы не конфликтовать с дефолтными
    пермишенами, которые RBAC сигнал создаёт при запуске тестовой БД
    (view_users, edit_users, view_roles и т.д.).
    """

    def test_create_persists_fields(self):
        # Создаём, перечитываем из БД — убеждаемся что оба поля сохранились.
        perm = Permission.objects.create(code="test__alpha", name="Тест Альфа")
        perm.refresh_from_db()
        self.assertEqual(perm.code, "test__alpha")
        self.assertEqual(perm.name, "Тест Альфа")

    def test_str_returns_name(self):
        perm = Permission.objects.create(code="test__beta", name="Тест Бета")
        self.assertEqual(str(perm), "Тест Бета")

    def test_code_is_unique(self):
        # unique=True на поле code — вторая запись с тем же кодом бросает IntegrityError.
        Permission.objects.create(code="test__gamma", name="Первый")
        with self.assertRaises(Exception):
            Permission.objects.create(code="test__gamma", name="Второй")


# ─────────────────────────── Role ─────────────────────────────────────────────


class RoleModelTests(TestCase):
    """Role — модель с code (unique), name, M2M к Permission.

    RBAC сигнал создаёт роли admin, department_head, specialist, auditor,
    all_seeing при запуске БД. Используем test__* коды чтобы не конфликтовать.
    """

    def test_create_persists_fields(self):
        role = Role.objects.create(code="test__admin_r", name="Тест Администратор")
        role.refresh_from_db()
        self.assertEqual(role.code, "test__admin_r")
        self.assertEqual(role.name, "Тест Администратор")

    def test_str_returns_name(self):
        role = Role.objects.create(code="test__spec_r", name="Тест Специалист")
        self.assertEqual(str(role), "Тест Специалист")

    def test_add_permission_via_m2m(self):
        # permissions — ManyToManyField. После add() пермишен виден через .all().
        perm = Permission.objects.create(code="test__dash_p", name="Тест Дашборд")
        role = Role.objects.create(code="test__aud_r", name="Тест Аудитор")
        role.permissions.add(perm)
        self.assertIn(perm, role.permissions.all())

    def test_role_without_permissions_is_valid(self):
        # blank=True на M2M — роль без пермишенов допустима.
        role = Role.objects.create(code="test__viewer_r", name="Тест Читатель")
        self.assertEqual(role.permissions.count(), 0)

    def test_role_code_is_unique(self):
        Role.objects.create(code="test__dept_r", name="Первый")
        with self.assertRaises(Exception):
            Role.objects.create(code="test__dept_r", name="Второй")


# ─────────────────────────── UserProfile ──────────────────────────────────────


class UserProfileModelTests(TestCase):
    """UserProfile — расширение User: роль, отделы, должность.

    UserProfile создаётся автоматически при создании User (сигнал
    signals_profile.py). В тестах мы создаём пользователя → достаём
    auto-созданный профиль → тестируем его.
    """

    def setUp(self):
        # setUp() вызывается перед каждым test_* методом.
        # create_user() → сигнал создаёт UserProfile со specialist-ролью.
        self.user = User.objects.create_user(
            username="ivan",
            email="ivan@test.com",
            password="testpass123",
        )
        self.profile = self.user.profile

        self.role = Role.objects.create(code="test_role", name="Тест роль")

    def test_profile_auto_created_with_user(self):
        # Сигнал create_user_profile должен создать профиль автоматически.
        self.assertIsNotNone(self.profile)
        self.assertEqual(self.profile.user, self.user)

    def test_departments_default_is_empty_list(self):
        # ArrayField с default=list — должно быть [], не None.
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.departments, [])

    def test_main_departments_default_is_empty_list(self):
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.main_departments, [])

    def test_head_of_departments_default_is_empty_list(self):
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.head_of_departments, [])

    def test_job_title_default_is_none(self):
        # null=True, blank=True — по умолчанию None.
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.job_title)

    def test_str_contains_username_and_role(self):
        # __str__ возвращает "username - role"
        self.profile.role = self.role
        self.profile.save()
        result = str(self.profile)
        self.assertIn(self.user.username, result)

    def test_is_role_returns_true_for_matching_code(self):
        self.profile.role = self.role
        self.profile.save()
        self.assertTrue(self.profile.is_role("test_role"))

    def test_is_role_returns_false_for_wrong_code(self):
        self.profile.role = self.role
        self.profile.save()
        self.assertFalse(self.profile.is_role("admin"))

    def test_is_role_returns_false_when_no_role(self):
        # role — FK с null=True. Если роли нет — is_role() должен вернуть False.
        self.profile.role = None
        self.profile.save()
        self.assertFalse(self.profile.is_role("anything"))

    # ── clean() — инварианты подмножеств ──────────────────────────────────────

    def test_clean_passes_when_main_is_subset_of_departments(self):
        # Инвариант: main_departments ⊆ departments. Здесь всё ок.
        self.profile.departments = ["DEPARTMENT_0"]
        self.profile.main_departments = ["DEPARTMENT_0"]
        self.profile.full_clean()  # не бросает — тест проходит

    def test_clean_raises_when_main_not_in_departments(self):
        # main_departments содержит отдел, которого нет в departments → ValidationError.
        self.profile.departments = ["DEPARTMENT_0"]
        self.profile.main_departments = ["DEPARTMENT_1"]  # не входит
        with self.assertRaises(ValidationError) as ctx:
            self.profile.full_clean()
        self.assertIn("main_departments", ctx.exception.message_dict)

    def test_clean_passes_when_head_is_subset_of_departments(self):
        self.profile.departments = ["DEPARTMENT_2"]
        self.profile.head_of_departments = ["DEPARTMENT_2"]
        self.profile.full_clean()  # ок

    def test_clean_raises_when_head_not_in_departments(self):
        # head_of_departments содержит отдел, которого нет в departments.
        self.profile.departments = ["DEPARTMENT_0"]
        self.profile.head_of_departments = ["DEPARTMENT_3"]
        with self.assertRaises(ValidationError) as ctx:
            self.profile.full_clean()
        self.assertIn("head_of_departments", ctx.exception.message_dict)

    def test_clean_passes_when_all_arrays_are_empty(self):
        # Пустые списки — инвариант соблюдён: ∅ ⊆ ∅.
        self.profile.departments = []
        self.profile.main_departments = []
        self.profile.head_of_departments = []
        self.profile.full_clean()

    # ── departments_summary() ──────────────────────────────────────────────────

    def test_departments_summary_empty_returns_empty_string(self):
        self.profile.departments = []
        self.assertEqual(self.profile.departments_summary(), "")

    def test_departments_summary_one_department(self):
        self.profile.departments = ["DEPARTMENT_0"]
        result = self.profile.departments_summary()
        self.assertIn("Research Team", result)

    def test_departments_summary_main_comes_first(self):
        # Основные отделы идут первыми в строке.
        self.profile.departments = ["DEPARTMENT_0", "DEPARTMENT_1"]
        self.profile.main_departments = ["DEPARTMENT_1"]
        result = self.profile.departments_summary()
        # Calibration Team (DEPARTMENT_1) должен быть РАНЬШЕ Research Team (DEPARTMENT_0)
        idx_main = result.find("Calibration Team")
        idx_other = result.find("Research Team")
        self.assertLess(idx_main, idx_other)

    def test_departments_summary_truncates_with_plus_suffix(self):
        # Если отделов больше limit=3, добавляется "+N".
        self.profile.departments = [
            "DEPARTMENT_0",
            "DEPARTMENT_1",
            "DEPARTMENT_2",
            "DEPARTMENT_3",
        ]
        result = self.profile.departments_summary(limit=3)
        self.assertIn("+1", result)

    def test_departments_summary_no_truncation_when_within_limit(self):
        # Ровно limit — суффикс не нужен.
        self.profile.departments = ["DEPARTMENT_0", "DEPARTMENT_1"]
        result = self.profile.departments_summary(limit=3)
        self.assertNotIn("+", result)

    def test_profile_deleted_when_user_deleted(self):
        # UserProfile.user — OneToOneField с on_delete=CASCADE.
        # Удаление User должно удалить и UserProfile.
        pk = self.profile.pk
        self.user.delete()
        self.assertFalse(UserProfile.objects.filter(pk=pk).exists())
