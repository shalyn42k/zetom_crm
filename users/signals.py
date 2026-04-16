from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from users.models import Role, UserProfile
from users.roles import ROLES
from zetom.models import Oferta, RequestMain, RequestNull

User = get_user_model()

print("SIGNALS LOADED")


# ---------------------------------------------------------
# 1. Создание профиля + автоматическое is_staff=True
# ---------------------------------------------------------
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:

        # Дать доступ в админку всем пользователям
        if not instance.is_staff:
            instance.is_staff = True
            instance.save(update_fields=["is_staff"])

        # Назначить первую доступную роль
        default_role = Role.objects.first()

        UserProfile.objects.get_or_create(
            user=instance, defaults={"role": default_role}
        )

        print(f"PROFILE CREATED FOR: {instance.username}")


# ---------------------------------------------------------
# 2. Автоматическое создание ролей после миграций
# ---------------------------------------------------------
@receiver(post_migrate)
def create_roles(sender, **kwargs):
    if sender.label != "zetom":
        return

    for role in ROLES:
        Role.objects.get_or_create(
            code=role["code"],
            defaults={"name": role["name"], "level": role.get("level", 0)},
        )


# ---------------------------------------------------------
# 3. Дать ВСЕМ пользователям view_* права,
#    чтобы Django не скрывал админку
# ---------------------------------------------------------
@receiver(post_migrate)
def give_view_permissions(sender, **kwargs):
    if sender.label != "zetom":
        return

    models = [RequestNull, RequestMain, Oferta]

    for model in models:
        ct = ContentType.objects.get_for_model(model)

        # Django создаёт view_* автоматически
        perm = Permission.objects.get(
            content_type=ct, codename=f"view_{model.__name__.lower()}"
        )

        # Дать право всем пользователям
        for user in User.objects.all():
            user.user_permissions.add(perm)

    print("VIEW PERMISSIONS APPLIED")
