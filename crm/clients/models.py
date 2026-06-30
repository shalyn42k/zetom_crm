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
