"""Сервис создания inapp-уведомлений (записей в `Notification`).

Зеркальный к mail_service, но кладёт записи в БД, а не отправляет SMTP.
Рендер не происходит на этапе создания — payload должен быть достаточно
самодостаточным, чтобы UI отрендерил шаблон в момент показа (это позволит
менять формулировку шаблона без миграции данных).
"""
# Stdlib
import logging

# Django imports
from django.contrib.contenttypes.models import ContentType

# Local imports
from crm.notification.models import Notification, NotificationKind

# claude
logger = logging.getLogger(__name__)


# claude
def _resolve_target(target):
    """Map a Django model instance to (ContentType, object_id) pair, or (None, None)."""
    if target is None:
        return None, None
    return ContentType.objects.get_for_model(type(target)), target.pk


# claude
def create_inapp(
    *,
    kind,
    template_name,
    payload,
    recipients,
    actor=None,
    target=None,
):
    """Create one `Notification` row per recipient.

    Arguments:
        kind: NotificationKind value (used by UI filters and the unread counter).
        template_name: path to the .txt template; UI renders it lazily.
        payload: JSON-serializable dict with everything the template needs.
        recipients: iterable of User instances.
        actor: User who triggered the event (or None for system events).
        target: optional model instance to link via GenericForeignKey; used in
                UI to render a "go to object" link.
    """
    if not recipients:
        logger.warning(
            "notification.inapp: skipping create, no recipients "
            "(kind=%r, template=%r)",
            kind,
            template_name,
        )
        return []

    if kind not in NotificationKind.values:
        logger.warning(
            "notification.inapp: unknown kind %r — defaulting to SYSTEM", kind
        )
        kind = NotificationKind.SYSTEM

    target_ct, target_id = _resolve_target(target)

    records = []
    for recipient in recipients:
        records.append(
            Notification.objects.create(
                recipient=recipient,
                actor=actor,
                kind=kind,
                template_name=template_name,
                payload=payload or {},
                target_content_type=target_ct,
                target_object_id=target_id,
            )
        )
    return records
