
from django.db import models
from django.contrib.auth import get_user_model




User = get_user_model()


# -----------------------------
# РОЛИ
# -----------------------------
class Role(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    level = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.name} ({self.code})"


# -----------------------------
# ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ
# -----------------------------
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.role}"

    # Получить конфигурацию роли
    def get_role_config(self):
        if not self.role:
            return {}
        from .permissions import ROLES_CONFIG
        return ROLES_CONFIG.get(self.role.code, {})

    def can_see_module(self, module_name: str) -> bool:
        cfg = self.get_role_config()
        modules = cfg.get("modules", [])
        return "*" in modules or module_name in modules

    def can_edit_model(self, model_name: str) -> bool:
        cfg = self.get_role_config()
        editable = cfg.get("can_edit_models", [])
        return "*" in editable or model_name in editable

    def is_model_readonly(self, model_name: str) -> bool:
        cfg = self.get_role_config()
        readonly = cfg.get("readonly_models", [])
        return "*" in readonly or model_name in readonly

    def is_model_hidden(self, model_name: str) -> bool:
        cfg = self.get_role_config()
        hidden = cfg.get("hidden_models", [])
        return "*" in hidden or model_name in hidden