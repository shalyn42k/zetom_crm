# Django imports
from django.contrib.auth.models import User
from django.contrib.postgres.fields import ArrayField
from django.core.validators import RegexValidator
from django.db import models
# Other imports
from phonenumber_field.modelfields import PhoneNumberField
# Other imports
from safedelete.config import SOFT_DELETE_CASCADE
from safedelete.models import SafeDeleteModel

# Zetom app imports
from crm.status_manager.services.statuses import RequestStatus, Status


class DepartmentsVariants(models.TextChoices):
    DEPARTMENT_0 = "DEPARTMENT_0", "Research Team"
    DEPARTMENT_1 = "DEPARTMENT_1", "Calibration Team"
    DEPARTMENT_2 = "DEPARTMENT_2", "Length and Angle Lab"
    DEPARTMENT_3 = "DEPARTMENT_3", "Electrical Lab"
    DEPARTMENT_4 = "DEPARTMENT_4", "Mechanical Lab"
    DEPARTMENT_5 = "DEPARTMENT_5", "Heating Equipment Lab"
    DEPARTMENT_6 = "DEPARTMENT_6", "Technical Office"

class RequestSource(models.TextChoices):
    PHONE = "phone", "Phone"
    EMAIL = "email", "Email"
    SITE = "site", "Site"
    PARENT = "main", "Parent"
    MANUAL = "manual", "Manual"
    OTHER = "other", "Other"



class RequestTemplate(SafeDeleteModel):
    _safedelete_policy = SOFT_DELETE_CASCADE
    source = models.CharField(choices=RequestSource.choices, default=RequestSource.OTHER, null=False, blank=False)
    assigned_to = models.ManyToManyField(User, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    first_name = models.CharField(max_length=50, blank=True, null=True)
    last_name = models.CharField(max_length=50, blank=True, null=True)
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
        blank=True,
        null=True,
    )
    message = models.TextField(null=True, blank=True)
    departments = ArrayField(
        models.CharField(max_length=30, choices=DepartmentsVariants.choices),
        default=list,
        blank=True,
    )

    class Meta:
        abstract = True

    @property
    def full_name(self):
        return " ".join(filter(None, (self.first_name, self.last_name)))

    def __str__(self):
        return f"{self.company_name}"


class RequestNull(RequestTemplate):
    class Meta:
        verbose_name = "Validation Window"
        verbose_name_plural = "Validation Window"


class RequestMain(RequestTemplate):
    status = models.CharField(max_length=20, choices=RequestStatus.choices, default=RequestStatus.active)
    from_null = models.OneToOneField(
        RequestNull, on_delete=models.SET_NULL, null=True, blank=True
    )
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
        verbose_name = "Offer"
        verbose_name_plural = "Offers"


class Zlecenie(RequestTemplate):
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.new)
    from_main = models.ForeignKey(
        RequestMain, on_delete=models.CASCADE, null=True, blank=True
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    deadline = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Order"
        verbose_name_plural = "Orders"


class Wniosek(RequestTemplate):
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.new)
    from_main = models.ForeignKey(
        RequestMain, on_delete=models.CASCADE, null=True, blank=True
    )
    notes = models.TextField(null=True, blank=True)
    application_number = models.CharField(max_length=20, null=True, blank=True)

    class Meta:
        verbose_name = "Application"
        verbose_name_plural = "Applications"

class DeletedRequest(RequestMain):  # proxy может открывать те же данные и в других классах 
    class Meta:
        proxy = True
        verbose_name = "Deleted Request"
        verbose_name_plural = "Deleted Requests"