from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField

# claude
from crm.clients.validators import normalize_nip, validate_nip


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

    def short_label(self):
        if self.company_name:
            return self.company_name
        return self.full_name or f"Client #{self.pk}"


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
