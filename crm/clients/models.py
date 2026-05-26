from django.db import models
from phonenumber_field.modelfields import PhoneNumberField

# claude
from crm.clients.validators import normalize_nip, validate_nip


class Client(models.Model):
    first_name = models.CharField("First name", max_length=100, blank=True, null=True)
    last_name = models.CharField("Last name", max_length=100, blank=True, null=True)

    company_name = models.CharField("Company name", max_length=255, blank=True, null=True)
    # claude — max_length=20 оставлен на случай исторических записей с разделителями;
    # новые значения нормализуются в clean() до 10 цифр.
    company_nip = models.CharField(
        "NIP", max_length=20, blank=True, null=True, db_index=True,
        validators=[validate_nip],
    )

    email = models.EmailField("Email", blank=True, null=True)
    phone = PhoneNumberField(null=True, blank=True)

    address = models.TextField("Address", blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Client"
        verbose_name_plural = "Clients"

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
