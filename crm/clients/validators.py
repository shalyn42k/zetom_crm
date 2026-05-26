# claude
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

NIP_WEIGHTS = (6, 5, 7, 2, 3, 4, 5, 6, 7)


def normalize_nip(value):
    """Принимает NIP в любой человеческой форме (`PL1234567890`,
    `123-456-32-18`, `123 456 32 18`, `123.456.32.18`) и возвращает строку из
    10 цифр. Если после очистки длина не 10 или встречаются нецифры —
    поднимает ValidationError."""
    if value is None:
        return value
    cleaned = "".join(ch for ch in str(value) if ch.isalnum())
    if cleaned[:2].upper() == "PL":
        cleaned = cleaned[2:]
    if len(cleaned) != 10 or not cleaned.isdigit():
        raise ValidationError(
            _("NIP must contain exactly 10 digits (separators and PL prefix are allowed).")
        )
    return cleaned


def validate_nip(value):
    """Валидатор для поля. Нормализует значение и проверяет контрольную сумму
    по официальной формуле (веса 6,5,7,2,3,4,5,6,7, mod 11)."""
    if value in (None, ""):
        return
    digits = normalize_nip(value)
    checksum = sum(int(d) * w for d, w in zip(digits, NIP_WEIGHTS)) % 11
    if checksum == 10 or checksum != int(digits[9]):
        raise ValidationError(_("Invalid NIP checksum."))
