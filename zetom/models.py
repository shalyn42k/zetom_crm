from django.core.validators import RegexValidator
from django.db import models
from django.contrib.auth.models import User
from phonenumber_field.modelfields import PhoneNumberField

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

class RequestTemplate(models.Model):
    phone = PhoneNumberField(blank=False)
    company_name = models.CharField(max_length=50, blank=True)
    email = models.EmailField(max_length=100, validators=[])
    company_nip = models.CharField(
        max_length=10,
        validators=[
            RegexValidator(
                regex=r"^\d{10}$", message="Your NIP sucks man, It must be 10 digits yo"
            )
        ],
        blank=True,
    )

    class Meta:
        permissions = [
            ("change_status", "Can change status"),
            ("assign_record", "Can assign record"),
            ("view_logs", "Can view logs"),
        ]
        abstract = True

    def __str__(self):
        return f"{self.company_name}"


class RequestNull(RequestTemplate):
    created_at = models.DateTimeField(auto_now_add=True)

class RequestMain(RequestTemplate):
    # Уникальные таблицы
    created_at = models.DateTimeField(auto_now_add=True)
    from_null = models.OneToOneField(RequestNull, on_delete=models.SET_NULL, null=True)
    full_name = models.CharField(max_length=50)
    address = models.CharField(max_length=50)
    notes = models.CharField(max_length=500)
    # вложение понять как сделать


class Oferta(RequestTemplate):
    # Уникальные таблички
    created_at = models.DateTimeField(auto_now_add=True)
    from_main = models.ForeignKey(RequestMain, on_delete=models.CASCADE, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
