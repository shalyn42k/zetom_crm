from django.db import models
from django.contrib.auth.models import User


class Role(models.Model):
    code = models.CharField(max_length=50, unique=True)  # admin, specialist, auditor...
    name = models.CharField(max_length=100)              # Человекочитаемое имя
    level = models.PositiveIntegerField(default=0)       # Иерархия ролей

    def __str__(self):
        return f"{self.name} ({self.code})"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.role}"


class Record(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)

    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    address = models.CharField(max_length=100)
    city = models.CharField(max_length=50)
    state = models.CharField(max_length=50)
    zipcode = models.CharField(max_length=20)

    class Meta:
        permissions = [
            ("change_status", "Can change status"),
            ("assign_record", "Can assign record"),
            ("view_logs", "Can view logs"),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
