from django.core.validators import RegexValidator
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField
from users.models import UserProfile, Role



# -----------------------------
# ОСНОВНЫЕ МОДЕЛИ ЗАЯВОК
# -----------------------------
class RequestTemplate(models.Model):
    phone = PhoneNumberField(blank=False)
    company_name = models.CharField(max_length=50, blank=True)
    email = models.EmailField(max_length=100)
    company_nip = models.CharField(
        max_length=10,
        validators=[
            RegexValidator(
                regex=r"^\d{10}$",
                message="Your NIP sucks man, It must be 10 digits yo"
            )
        ],
        blank=True,
    )

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.company_name}"


class RequestNull(RequestTemplate):
    created_at = models.DateTimeField(auto_now_add=True)


class RequestMain(RequestTemplate):
    created_at = models.DateTimeField(auto_now_add=True)
    from_null = models.OneToOneField(RequestNull, on_delete=models.SET_NULL, null=True)
    full_name = models.CharField(max_length=50)
    address = models.CharField(max_length=50)
    notes = models.CharField(max_length=500)


class Oferta(RequestTemplate):
    created_at = models.DateTimeField(auto_now_add=True)
    from_main = models.ForeignKey(RequestMain, on_delete=models.CASCADE, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)

