"""Thin wrappers для двух исторических точек интеграции:
сайтовая форма (RequestNull → стафф) и admin-валидация (RequestMain → стафф).

Оставлены отдельно от request_mail.py для обратной совместимости имён,
импортируемых из crm/zetom. Никакой бизнес-логики тут нет — только сборка
контекста и зов mail_service с получателями из services/recipients.
"""
# Django imports
from django.template.loader import render_to_string

# Local imports
from crm.notification.services import mail_service
from crm.notification.services.recipients import dep_heads_or_admins_emails
from crm.notification.services.request_mail import _split_subject_body
from crm.zetom.models import RequestMain, RequestNull

REQUEST_NEW_TEMPLATE = "notification/mail/staff/request_new.txt"
REQUEST_VALIDATED_TEMPLATE = "notification/mail/staff/request_validated.txt"


# claude
def send_notification_to_staff(request_object: RequestNull):
    """Triggered by the public site form (`views.email_template`).

    RequestNull has no departments resolution path yet — until the staff
    validates it, we have no way to pick a dep_head. Fallback to admins
    via `dep_heads_or_admins_emails` (which on empty `departments` already
    falls back to admins).
    """
    rendered = render_to_string(REQUEST_NEW_TEMPLATE, {"request": request_object})
    subject, body = _split_subject_body(rendered)
    mail_service.send_to_staff(
        subject=subject,
        body=body,
        recipients=dep_heads_or_admins_emails(request_object),
        template_name=REQUEST_NEW_TEMPLATE,
        payload={"request_id": request_object.pk, "stage": "new"},
    )


# claude
def send_notification_approve_null(request_object: RequestMain):
    """Triggered when staff validates a RequestNull and a RequestMain is born."""
    rendered = render_to_string(REQUEST_VALIDATED_TEMPLATE, {"request": request_object})
    subject, body = _split_subject_body(rendered)
    mail_service.send_to_staff(
        subject=subject,
        body=body,
        recipients=dep_heads_or_admins_emails(request_object),
        template_name=REQUEST_VALIDATED_TEMPLATE,
        payload={"request_id": request_object.pk, "stage": "validated"},
    )
