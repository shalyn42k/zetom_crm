# Django imports
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.db import models
# Other imports
from phonenumber_field.modelfields import PhoneNumberField
# Other imports
from safedelete.config import SOFT_DELETE_CASCADE
from safedelete.models import SafeDeleteModel

# Zetom app imports
from crm.zetom.services.statuses import ArchiveState, Status

# Users app imports
# from crm.users.models import Role, UserProfile



class DepartmentsVariants(models.TextChoices):
    DEPARTMENT_0 = "DEPARTMENT_0", "Zespół ds. Badań"
    DEPARTMENT_1 = "DEPARTMENT_1", "Zespół ds. Wzorcowań"
    DEPARTMENT_2 = "DEPARTMENT_2", "Pracownia Długości i Kąta"
    DEPARTMENT_3 = "DEPARTMENT_3", "Pracownia Elektrotechniczna"
    DEPARTMENT_4 = "DEPARTMENT_4", "Pracownia Mechaniczna"
    DEPARTMENT_5 = "DEPARTMENT_5", "Pracownia Urządzeń Grzewczych"
    DEPARTMENT_6 = "DEPARTMENT_6", "Biuro Techniczne"




class RequestTemplate(SafeDeleteModel):
    _safedelete_policy = SOFT_DELETE_CASCADE
    assigned_to = models.ManyToManyField(User, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    phone = PhoneNumberField(null=False, blank=False)
    company_name = models.CharField(max_length=50, blank=True, null=True)
    email = models.EmailField(max_length=100, null=False, blank=False)
    company_nip = models.CharField(
        max_length=10,
        validators=[
            RegexValidator(
                regex=r"^\d{10}$"
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
        null=True,
        blank=True,
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
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.new)
    is_archived = models.BooleanField(default=False)
    from_null = models.OneToOneField(
        RequestNull, on_delete=models.SET_NULL, null=True, blank=True
    )
    full_name = models.CharField(max_length=50, null=True, blank=True)
    address = models.CharField(max_length=228, null=True, blank=True)

    class Meta:
        verbose_name = "Information"
        verbose_name_plural = "Information"


class Oferta(RequestTemplate):
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.new)
    from_main = models.ForeignKey(
        RequestMain, on_delete=models.CASCADE, null=True, blank=True
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = "Oferta Information"
        verbose_name_plural = "Oferta Information"


class Zlecenie(RequestTemplate):
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.new)
    from_main = models.ForeignKey(
        RequestMain, on_delete=models.CASCADE, null=True, blank=True
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    deadline = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Zlecenie Information"
        verbose_name_plural = "Zlecenie Information"


class Wniosek(RequestTemplate):
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.new)
    from_main = models.ForeignKey(
        RequestMain, on_delete=models.CASCADE, null=True, blank=True
    )
    notes = models.TextField(null=True, blank=True)
    application_number = models.CharField(max_length=20, null=True, blank=True)

    class Meta:
        verbose_name = "Wniosek Information"
        verbose_name_plural = "Wniosek Information"
