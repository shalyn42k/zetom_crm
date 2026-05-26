"""Высокоуровневые сценарии рассылки по RequestMain и дочкам (Oferta/Zlecenie/Wniosek).

Точка входа для view'ев "Actions → Mail" и автотриггеров из сигналов.
Здесь живут выбор шаблона, рендер, резолв получателей и пост-эффекты
(например, флип статуса документа `in_progress → waiting`). Реальной
отправкой занимается mail_service; никаких прямых send_mail тут нет.
"""
# Django imports
from django.template.loader import render_to_string

# Local imports
from crm.notification.services import mail_service
from crm.notification.services.recipients import default_recipients_emails
from crm.status_manager.services.statuses import Status

# claude — Dispatch tables keyed by document class name (string).
# Using type(...).__name__ avoids importing the zetom models here (the
# top-level docstring asks to keep cross-app imports local) and lets the
# dispatch grow without restructuring the file.
_STAFF_TEMPLATE = {
    "Oferta": "notification/mail/oferta_staff.txt",
    "Zlecenie": "notification/mail/zlecenie_staff.txt",
    "Wniosek": "notification/mail/wniosek_staff.txt",
}
_DOC_PREFIX = {
    "Oferta": "OFR",
    "Zlecenie": "ZLC",
    "Wniosek": "WNI",
}
_DOC_KIND_RU = {
    "Oferta": "оферта",
    "Zlecenie": "заказ",
    "Wniosek": "заявление",
}

CLIENT_IN_PROGRESS_TEMPLATE = "notification/mail/client_in_progress.txt"


# claude
def _document_kind(document):
    return type(document).__name__


# claude
def _document_code(document):
    """Short human code like OFR-2026-0042; used in client template subjects."""
    prefix = _DOC_PREFIX.get(_document_kind(document), "DOC")
    year = document.created_at.year
    return f"{prefix}-{year}-{document.pk:04d}"


# claude
def _split_subject_body(rendered):
    """Convention: first non-empty line is the subject, the rest is the body.

    Leading whitespace (typical leftover from a `{% comment %}` block at the
    top of the file) is stripped before splitting.
    """
    stripped = rendered.lstrip()
    if "\n" in stripped:
        subject, body = stripped.split("\n", 1)
    else:
        subject, body = stripped, ""
    return subject.strip(), body.lstrip("\n")


# claude
def send_document_to_staff(document, actor=None):
    if document.status != Status.in_progress:
        return

    kind = _document_kind(document)
    template_name = _STAFF_TEMPLATE.get(kind)
    if template_name is None:
        return

    parent = document.from_main
    rendered = render_to_string(template_name, {
        "document": document,
        "parent": parent,
        "sender": actor,
    })
    subject, body = _split_subject_body(rendered)

    recipients = default_recipients_emails(parent) if parent else []
    mail_service.send_to_staff(
        subject=subject,
        body=body,
        recipients=recipients,
        template_name=template_name,
        payload={
            "document_id": document.pk,
            "document_kind": kind,
            "request_id": parent.pk if parent else None,
        },
        actor=actor,
    )

    document.status = Status.waiting
    document.save(update_fields=["status"])


# claude
def send_document_to_client(document):
    parent = document.from_main
    to = document.email or (parent.email if parent else "")
    if not to:
        return

    kind = _document_kind(document)
    rendered = render_to_string(CLIENT_IN_PROGRESS_TEMPLATE, {
        "document": document,
        "parent": parent,
        "document_kind": _DOC_KIND_RU.get(kind, kind.lower()),
        "document_code": _document_code(document),
    })
    subject, body = _split_subject_body(rendered)

    mail_service.send_to_client(
        to=to,
        subject=subject,
        body=body,
        template_name=CLIENT_IN_PROGRESS_TEMPLATE,
        payload={
            "document_id": document.pk,
            "document_kind": kind,
            "request_id": parent.pk if parent else None,
        },
    )


# claude
def send_freeform_to_client(*, request_main, subject, body, from_user):
    if not request_main.email:
        return
    mail_service.send_to_client(
        to=request_main.email,
        subject=subject,
        body=body,
        template_name="",
        payload={"request_id": request_main.pk},
        actor=from_user,
    )
