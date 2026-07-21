from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField

# claude
from crm.clients.validators import normalize_nip, validate_nip


# claude
class ClientType(models.TextChoices):
    PERSON = "person", _("Person / FOP")
    COMPANY = "company", _("Company / Firm")


class Client(models.Model):
    first_name = models.CharField(_("First name"), max_length=100, blank=True, null=True)
    last_name = models.CharField(_("Last name"), max_length=100, blank=True, null=True)

    company_name = models.CharField(_("Company name"), max_length=255, blank=True, null=True)
    # claude — max_length=20 оставлен на случай исторических записей с разделителями;
    # новые значения нормализуются в clean() до 10 цифр.
    company_nip = models.CharField(
        _("NIP"), max_length=20, blank=True, null=True, db_index=True,
        validators=[validate_nip],
    )

    email = models.EmailField(_("Email"), blank=True, null=True)
    phone = PhoneNumberField(null=True, blank=True)

    address = models.TextField(_("Address"), blank=True, null=True)

    # claude
    client_type = models.CharField(
        _("Client type"),
        max_length=20,
        choices=ClientType.choices,
        default=ClientType.PERSON,
        help_text=_("FOP/osoba fizyczna or Firma/spółka"),
    )
    # claude
    notes = models.TextField(_("Notes"), blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Client")
        verbose_name_plural = _("Clients")

    # claude
    def clean(self):
        super().clean()
        if self.company_nip:
            self.company_nip = normalize_nip(self.company_nip)

    def __str__(self):
        if self.company_name:
            return f"{self.company_name} ({self.company_nip or 'no NIP'})"
        if self.first_name or self.last_name:
            return f"{self.first_name or ''} {self.last_name or ''}".strip()
        return f"Client #{self.pk}"

    def full_name(self):
        return f"{self.first_name or ''} {self.last_name or ''}".strip()

    # claude
    def short_label(self):
        if self.company_name:
            return self.company_name
        return self.full_name() or f"Client #{self.pk}"


class ClientInteraction(models.Model):
    """БАГ-9 + БАГ-10: история контактов с клиентом — канал, суть, участники."""

    class Channel(models.TextChoices):
        CALL = "call", _("Call")
        EMAIL = "email", _("Email")
        MEETING = "meeting", _("Meeting")
        CHAT = "chat", _("Chat")
        OTHER = "other", _("Other")

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="interactions",
        verbose_name=_("Client"),
    )
    # Заявка, в рамках которой был контакт (необязательно)
    request = models.ForeignKey(
        "zetom.RequestMain",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="client_interactions",
        verbose_name=_("Request"),
    )
    channel = models.CharField(
        max_length=20,
        choices=Channel.choices,
        verbose_name=_("Channel"),
    )
    summary = models.TextField(verbose_name=_("Summary"))
    # Сотрудник, который контактировал
    contacted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="client_interactions",
        verbose_name=_("Contacted by"),
    )
    # Контактное лицо со стороны клиента (имя, должность — свободный текст)
    contact_person = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Contact person"),
    )
    contacted_at = models.DateTimeField(verbose_name=_("Contacted at"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Client interaction")
        verbose_name_plural = _("Client interactions")
        ordering = ["-contacted_at"]

    def __str__(self):
        return f"{self.get_channel_display()} · {self.client} · {self.contacted_at:%Y-%m-%d}"


# claude
class SupplierType(models.TextChoices):
    LOCAL = "lokalny", _("Lokalny")
    REGIONAL = "regionalny", _("Regionalny")
    INTERNATIONAL = "miedzynarodowy", _("Międzynarodowy")


# claude
class Company(models.Model):
    """Фирма (Klient/Firma). Нормализованная сущность взамен текст-полей
    company_name/company_nip на Client."""

    name = models.CharField(_("Name"), max_length=255)
    short_name = models.CharField(_("Short name"), max_length=255, blank=True)
    full_name = models.CharField(_("Full name"), max_length=500, blank=True)

    nip = models.CharField(
        _("NIP"), max_length=20, blank=True, null=True, db_index=True,
        validators=[validate_nip],
    )
    regon = models.CharField(_("REGON"), max_length=14, blank=True)
    type_supplier = models.CharField(
        _("Supplier type"), max_length=20, choices=SupplierType.choices, blank=True,
    )

    country = models.CharField(_("Country"), max_length=100, blank=True)
    city = models.CharField(_("City"), max_length=100, blank=True)
    voivodeship = models.CharField(_("Voivodeship"), max_length=100, blank=True)
    post_code = models.CharField(_("Post code"), max_length=20, blank=True)
    street = models.CharField(_("Street"), max_length=255, blank=True)

    phone = PhoneNumberField(_("Phone"), null=True, blank=True)
    email = models.EmailField(_("Email"), blank=True)

    comments = models.TextField(_("Comments"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Company")
        verbose_name_plural = _("Companies")
        # claude
        constraints = [
            models.UniqueConstraint(
                fields=["nip"],
                condition=models.Q(nip__isnull=False),
                name="uniq_company_nip",
            ),
        ]

    def clean(self):
        super().clean()
        if self.nip:
            self.nip = normalize_nip(self.nip)

    def __str__(self):
        if self.nip:
            return f"{self.name} ({self.nip})"
        return self.name or f"Company #{self.pk}"


# claude
class CompanyPersonLink(models.Model):
    """M2M связь Company ↔ Client(=Person) с должностью. Человек может быть в
    нескольких фирмах (несколько связей)."""

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="person_links",
        verbose_name=_("Company"),
    )
    person = models.ForeignKey(
        "clients.Client", on_delete=models.CASCADE, related_name="company_links",
        verbose_name=_("Person"),
    )
    position = models.CharField(_("Position"), max_length=255, blank=True)
    is_primary = models.BooleanField(_("Primary contact"), default=False)
    linked_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name=_("Linked by"),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Company contact")
        verbose_name_plural = _("Company contacts")
        constraints = [
            models.UniqueConstraint(
                fields=["company", "person"], name="uniq_company_person",
            ),
        ]

    def __str__(self):
        return f"{self.person_id} @ {self.company_id}"
