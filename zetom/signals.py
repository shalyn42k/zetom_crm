from django.contrib.auth.models import Permission, User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile
from .permissions import ROLE_PERMISSIONS


# Создание профиля при создании пользователя
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


# Назначение прав при создании или обновлении профиля
@receiver(post_save, sender=UserProfile)
def assign_role_permissions(sender, instance, **kwargs):
    user = instance.user
    role = instance.role

    if role is None:
        return

    role_code = role.code
    perms = ROLE_PERMISSIONS.get(role_code, [])

    # Если роль all_seeing — дать все права
    if "*" in perms:
        user.user_permissions.set(Permission.objects.all())
        return

    # Очистить старые права
    user.user_permissions.clear()

    # Назначить права по роли
    for perm_code in perms:
        try:
            perm = Permission.objects.get(codename=perm_code)
            user.user_permissions.add(perm)
        except Permission.DoesNotExist:
            pass
