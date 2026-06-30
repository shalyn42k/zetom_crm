# Django imports
from django.contrib.auth.models import User
from django.contrib.postgres.fields import ArrayField
from django.db import models
# Other imports
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField
from simple_history.models import HistoricalRecords
# Other imports
from safedelete.config import SOFT_DELETE_CASCADE
from safedelete.models import SafeDeleteModel

# claude
from crm.clients.validators import normalize_nip, validate_nip
# Zetom app imports
from crm.status_manager.services.statuses import RequestStatus, Status


class DepartmentsVariants(models.TextChoices):
    DEPARTMENT_0 = "DEPARTMENT_0", _("Research Team")
    DEPARTMENT_1 = "DEPARTMENT_1", _("Calibration Team")
    DEPARTMENT_2 = "DEPARTMENT_2", _("Length and Angle Lab")
    DEPARTMENT_3 = "DEPARTMENT_3", _("Electrical Lab")
    DEPARTMENT_4 = "DEPARTMENT_4", _("Mechanical Lab")
    DEPARTMENT_5 = "DEPARTMENT_5", _("Heating Equipment Lab")
    DEPARTMENT_6 = "DEPARTMENT_6", _("Technical Office")

class RequestSource(models.TextChoices):
    PHONE = "phone", _("Phone")
    EMAIL = "email", _("Email")
    SITE = "site", _("Site")
    PARENT = "main", _("Parent")
    MANUAL = "manual", _("Manual")
    OTHER = "other", _("Other")



class RequestTemplate(SafeDeleteModel):
    _safedelete_policy = SOFT_DELETE_CASCADE
    source = models.CharField(choices=RequestSource.choices, default=RequestSource.OTHER, null=False, blank=False, verbose_name=_("Source"))
    assigned_to = models.ManyToManyField(User, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))
    first_name = models.CharField(max_length=50, blank=True, null=True)
    last_name = models.CharField(max_length=50, blank=True, null=True)
    phone = PhoneNumberField(null=False, blank=False, verbose_name=_("Phone"))
    company_name = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("Company name"))
    email = models.EmailField(max_length=100, null=False, blank=False, verbose_name=_("Email"))
    # claude — max_length=20 чтобы пользователь мог ввести `PL...`, дефисы и пробелы;
    # clean() приведёт значение к 10 цифрам перед сохранением.
    company_nip = models.CharField(
        max_length=20,
        validators=[validate_nip],
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

    # claude
    def clean(self):
        super().clean()
        if self.company_nip:
            self.company_nip = normalize_nip(self.company_nip)

    @property
    def full_name(self):
        return " ".join(filter(None, (self.first_name, self.last_name)))

    def __str__(self):
        return f"{self.company_name}"


class RequestNull(RequestTemplate):
    class Meta:
        verbose_name = _("Validation Window")
        verbose_name_plural = _("Validation Window")


class RequestMain(RequestTemplate):
    status = models.CharField(max_length=20, choices=RequestStatus.choices, default=RequestStatus.active)
    from_null = models.OneToOneField(
        RequestNull, on_delete=models.SET_NULL, null=True, blank=True
    )
    address = models.CharField(max_length=228, null=True, blank=True)
    # claude — per-Req флаг "owner". owners ⊆ assigned_to поддерживается на
    # уровне UI/admin-actions (set_owner доступен только для assigned юзеров,
    # unassign снимает owner-флаг). Подробности в memory:
    # project_per_req_permissions.md.
    owners = models.ManyToManyField(
        User,
        blank=True,
        related_name="owned_requests",
    )
    # claude — M2M к Client через RequestClientLink. Заявка может быть
    # привязана к нескольким клиентам (похожий/идентичный клиент или
    # компания), и при этом продолжать существовать самостоятельно.
    # Persisted relation, в отличие от form-only ClientField (autofill).
    clients = models.ManyToManyField(
        "clients.Client",
        through="RequestClientLink",
        related_name="requests",
        blank=True,
    )
    # БАГ-2: полная история всех изменений полей (кто/что/когда изменил)
    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Information")
        verbose_name_plural = _("Information")


class Oferta(RequestTemplate):
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.new)
    from_main = models.ForeignKey(
        RequestMain, on_delete=models.CASCADE, null=True, blank=True, verbose_name=_("From main")
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = _("Offer")
        verbose_name_plural = _("Offers")


class Zlecenie(RequestTemplate):
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.new)
    from_main = models.ForeignKey(
        RequestMain, on_delete=models.CASCADE, null=True, blank=True, verbose_name=_("From main")
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    deadline = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")


class Wniosek(RequestTemplate):
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.new)
    from_main = models.ForeignKey(
        RequestMain, on_delete=models.CASCADE, null=True, blank=True, verbose_name=_("From main")
    )
    notes = models.TextField(null=True, blank=True)
    application_number = models.CharField(max_length=20, null=True, blank=True)

    class Meta:
        verbose_name = _("Application")
        verbose_name_plural = _("Applications")

# claude — through-таблица для RequestMain.clients (M2M).
# linked_by/linked_at дают аудит: кто и когда привязал клиента к заявке.
class RequestClientLink(models.Model):
    request = models.ForeignKey(
        RequestMain, on_delete=models.CASCADE, related_name="client_links"
    )
    client = models.ForeignKey(
        "clients.Client", on_delete=models.CASCADE, related_name="request_links"
    )
    linked_at = models.DateTimeField(auto_now_add=True)
    linked_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["request", "client"], name="uniq_request_client"
            ),
        ]
        verbose_name = _("Client link")
        verbose_name_plural = _("Client links")

    def __str__(self):
        return f"{self.request_id} ↔ {self.client_id}"


class RequestAttachment(models.Model):
    """БАГ-8: файловые вложения к заявке (RequestNull → после валидации RequestMain)."""
    request_null = models.ForeignKey(
        RequestNull,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
    )
    request_main = models.ForeignKey(
        RequestMain,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
    )
    file = models.FileField(upload_to="request_attachments/%Y/%m/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = _("Attachment")
        verbose_name_plural = _("Attachments")

    def __str__(self):
        return self.file.name


class DeletedRequest(RequestMain):  # proxy может открывать те же данные и в других классах
    class Meta:
        proxy = True
        verbose_name = _("Deleted Request")
        verbose_name_plural = _("Deleted Requests")

class CancelledRequest(RequestMain):
    class Meta:
        proxy = True
        verbose_name = _("Cancelled Request")
        verbose_name_plural = _("Cancelled Requests")