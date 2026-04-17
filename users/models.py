from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()



class Role(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    level = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.name} ({self.code})"



class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.role}"

    