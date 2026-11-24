from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from crm.users.models import Role, UserProfile

User = get_user_model()


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):

    if not created:
        return

    
    if hasattr(instance, "profile"):
        return

    default_role, _ = Role.objects.get_or_create(
        code="specialist", defaults={"name": "Specialist"}
    )

    UserProfile.objects.create(user=instance, role=default_role)
