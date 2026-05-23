"""Низкоуровневая обёртка над django.core.mail.send_mail.

Единственная точка реальной отправки в модуле notification. Принимает уже
отрендеренные subject/body, шаблонной логики тут нет — это уровень
request_mail.py. На каждое письмо создаёт запись `EmailNotification` со
статусом PENDING → SENT/FAILED для аудита; SMTP-исключения гасятся, чтобы
не валить вызывающий view/сигнал.
"""
# Stdlib
import logging

# Django imports
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

# Local imports
from crm.notification.models import EmailNotification, EmailStatus

# claude
logger = logging.getLogger(__name__)


# claude
def _send(*, recipients, subject, body, template_name="", payload=None, actor=None):
    """One EmailNotification per recipient + send_mail per recipient.

    Records are created in PENDING before the SMTP call. On success — flip to
    SENT and stamp sent_at. On failure — flip to FAILED and store the exception
    string in status_reason. Exception is logged but NOT re-raised: SMTP fail
    must not break the calling view or signal.

    Per-recipient send_mail loop (vs one send_mail with the full list) so the
    log table tells us exactly which addresses succeeded.
    """
    if not recipients:
        logger.warning(
            "notification.mail: skipping send, no recipients "
            "(subject=%r, template=%r)",
            subject,
            template_name,
        )
        return []

    records = []
    for email in recipients:
        record = EmailNotification.objects.create(
            recipient_email=email,
            actor=actor,
            template_name=template_name,
            subject=subject,
            payload=payload or {},
            status=EmailStatus.PENDING,
        )
        try:
            send_mail(
                subject,
                body,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
            )
        except Exception as exc:
            record.status = EmailStatus.FAILED
            record.status_reason = str(exc)
            record.save(update_fields=["status", "status_reason"])
            logger.exception("notification.mail: failed to send to %s", email)
        else:
            record.status = EmailStatus.SENT
            record.sent_at = timezone.now()
            record.save(update_fields=["status", "sent_at"])
        records.append(record)
    return records


# claude
def send_to_client(*, to, subject, body, template_name="", payload=None, actor=None):
    """Send a single email to a client address."""
    return _send(
        recipients=[to],
        subject=subject,
        body=body,
        template_name=template_name,
        payload=payload,
        actor=actor,
    )


# claude
def send_to_staff(*, subject, body, recipients, template_name="", payload=None, actor=None):
    """Send an email to staff.

    `recipients` is required and is expected to be resolved dynamically via
    `services/recipients.py` (dep_heads_or_admins_emails / specialists / etc.)
    for the specific Req context. Empty list is allowed — `_send` will skip
    with a warning instead of raising.
    """
    return _send(
        recipients=recipients,
        subject=subject,
        body=body,
        template_name=template_name,
        payload=payload,
        actor=actor,
    )
