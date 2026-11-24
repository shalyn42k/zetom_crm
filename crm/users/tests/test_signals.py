# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ СИГНАЛОВ users
#
# signals_profile.py:
#   @receiver(post_save, sender=User)
#   def create_user_profile(sender, instance, created, **kwargs):
#       • Если created=True и профиля ещё нет → создаёт UserProfile со specialist ролью
#       • Если created=False (update) → ничего не делает
#       • Если профиль уже есть → ничего не делает (guard: hasattr(instance, 'profile'))
#
# Почему важно тестировать сигналы отдельно:
#   Сигнал — это неявное поведение. Если его сломать, формы и вьюшки начнут
#   падать с RelatedObjectDoesNotExist. Тест явно документирует этот инвариант.
# ──────────────────────────────────────────────────────────────────────────────

from django.contrib.auth import get_user_model
from django.test import TestCase

from crm.users.models import Role, UserProfile

User = get_user_model()


class CreateUserProfileSignalTests(TestCase):

    def test_creating_user_creates_profile(self):
        # post_save(created=True) → сигнал создаёт UserProfile.
        user = User.objects.create_user(username="signaltest", password="x")
        self.assertTrue(hasattr(user, "profile"))
        self.assertIsNotNone(user.profile)

    def test_profile_linked_to_created_user(self):
        user = User.objects.create_user(username="linktest", password="x")
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.user, user)

    def test_profile_role_is_specialist_by_default(self):
        # Сигнал назначает роль "specialist" (get_or_create).
        user = User.objects.create_user(username="roletest", password="x")
        profile = UserProfile.objects.get(user=user)
        self.assertIsNotNone(profile.role)
        self.assertEqual(profile.role.code, "specialist")

    def test_updating_user_does_not_create_second_profile(self):
        # post_save(created=False) → сигнал не должен создавать ещё один профиль.
        user = User.objects.create_user(username="updatetest", password="x")
        count_before = UserProfile.objects.filter(user=user).count()

        # Обновляем email → сигнал сработает с created=False.
        user.email = "updated@test.com"
        user.save()

        count_after = UserProfile.objects.filter(user=user).count()
        self.assertEqual(count_before, count_after)

    def test_specialist_role_created_if_not_exists(self):
        # Сигнал создаёт роль "specialist" через get_or_create если её нет.
        # Удаляем существующую роль specialist, если есть.
        Role.objects.filter(code="specialist").delete()

        user = User.objects.create_user(username="newrole", password="x")
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.role.code, "specialist")

    def test_one_to_one_accessed_via_profile_attribute(self):
        # Стандартный Django OneToOneField создаёт обратный accessor .profile
        user = User.objects.create_user(username="accessortest", password="x")
        self.assertEqual(user.profile.user_id, user.pk)
