# Django imports
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.db import models

# Other imports
from phonenumber_field.modelfields import PhoneNumberField
from safedelete.models import SafeDeleteModel

# Users app imports
# from crm.users.models import Role, UserProfile


class DepartmentsVariants(models.TextChoices):
    DEPARTMENT_0 = "DEPARTMENT_0", "department 1"
    DEPARTMENT_1 = "DEPARTMENT_1", "department 2"
    DEPARTMENT_2 = "DEPARTMENT_2", "department 3"
    DEPARTMENT_3 = "DEPARTMENT_3", "department 4"

class RequestTemplate(SafeDeleteModel):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    phone = PhoneNumberField(null=False, blank=False)
    company_name = models.CharField(max_length=50, blank=True, null=True)
    email = models.EmailField(max_length=100, null=False, blank=False)
    company_nip = models.CharField(
        max_length=10,
        validators=[
            RegexValidator(
                regex=r"^\d{10}$", message="Your NIP sucks man, It must be 10 digits yo"
            )
        ],
        blank=False,
        null=False,
    )
    message = models.TextField(null=True, blank=True)
    department = models.CharField(
        max_length=30,
        choices=DepartmentsVariants, 
        default=DepartmentsVariants.DEPARTMENT_0,
        null = True,
        blank=True
        )

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.company_name}"


class RequestNull(RequestTemplate):
    class Meta:
        verbose_name = "Validation Window"
        verbose_name_plural = "Validation Window"


class RequestMain(RequestTemplate):
    from_null = models.OneToOneField(
        RequestNull, on_delete=models.SET_NULL, null=True, blank=True
    )
    full_name = models.CharField(max_length=50, null=True, blank=True)
    address = models.CharField(max_length=228, null=True, blank=True)
    # вложение понять как сделать

    class Meta:
        verbose_name = "Information"
        verbose_name_plural = "Information"


class Oferta(RequestTemplate):
    from_main = models.ForeignKey(
        RequestMain, on_delete=models.CASCADE, null=True, blank=True
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = "Oferta Information"
        verbose_name_plural = "Oferta Information"
