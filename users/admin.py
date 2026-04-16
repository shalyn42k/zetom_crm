from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Role, UserProfile


def get_profile(user):
    """Безопасно возвращает профиль или None."""
    if not user.is_authenticated:
        return None
    try:
        return user.profile
    except UserProfile.DoesNotExist:
        return None


# =========================================================
# Role & UserProfile
# =========================================================
@admin.register(Role)
class AdminRole(ModelAdmin):
    list_display = ("code", "name", "level")


@admin.register(UserProfile)
class AdminUserProfile(ModelAdmin):
    list_display = ("user", "role")
