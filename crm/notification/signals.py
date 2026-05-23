"""Сигналы для автоотправки писем при смене статуса дочерних документов.

Триггер Б из ТЗ: когда `Oferta` / `Zlecenie` / `Wniosek` переходит в
`Status.in_progress`, клиенту автоматически уходит письмо. Сигналы живут
здесь (а не в `status_manager/signals.py`), потому что рассылка — это
доменная зона `notification`, а status_manager занимается только своей
каскадной логикой.

Чтобы Django подхватил эти ресиверы, в `apps.py.ready()` импортируется
этот модуль.
"""
# Django imports
from django.db.models.signals import post_save, pre_save

# Local imports
from crm.notification.models import NotificationKind
from crm.notification.services import inapp_service, request_mail
from crm.notification.services.recipients import dep_heads_or_admins
from crm.status_manager.services.statuses import Status
from crm.zetom.models import Oferta, RequestMain, Wniosek, Zlecenie

# claude
_DOCUMENT_MODELS = (Oferta, Zlecenie, Wniosek)
REQUEST_STATUS_CHANGED_TEMPLATE = "notification/inapp/staff/request_status_changed.txt"


# claude
def _capture_old_status(sender, instance, **kwargs):
    """Snapshot pre-save status onto the instance for post_save to compare.

    Django's post_save doesn't expose the previous DB state, so we hand it
    over via a temporary attribute. For unsaved (new) instances there's no
    "old" status — we set None so the comparison still works.
    """
    if not instance.pk:
        instance._old_status = None
        return
    try:
        instance._old_status = sender.objects.get(pk=instance.pk).status
    except sender.DoesNotExist:
        instance._old_status = None


# claude
def _send_client_on_in_progress(sender, instance, created, **kwargs):
    """If the document just transitioned into in_progress, email the client."""
    old = getattr(instance, "_old_status", None)
    if old != instance.status and instance.status == Status.in_progress:
        request_mail.send_document_to_client(instance)


# claude — wire the pair of receivers for each of the three document models
for _model in _DOCUMENT_MODELS:
    pre_save.connect(
        _capture_old_status,
        sender=_model,
        dispatch_uid=f"notification.capture_old_status.{_model.__name__}",
    )
    post_save.connect(
        _send_client_on_in_progress,
        sender=_model,
        dispatch_uid=f"notification.send_client_on_in_progress.{_model.__name__}",
    )


# claude
def _notify_inapp_on_request_status_change(sender, instance, created, **kwargs):
    """RequestMain status change → inapp notification for dep_heads/admins.

    `_old_status` is captured by the same `_capture_old_status` pre_save
    receiver (it works on any sender that has a `status` field).
    Actor is read from a temporary `instance._actor` attribute that views
    set before saving — signals don't have access to request.user.
    """
    if created:
        return  # creation handled elsewhere (validation flow)
    old = getattr(instance, "_old_status", None)
    if old is None or old == instance.status:
        return

    actor = getattr(instance, "_actor", None)
    recipients = dep_heads_or_admins(instance)
    inapp_service.create_inapp(
        kind=NotificationKind.STATUS_CHANGE,
        template_name=REQUEST_STATUS_CHANGED_TEMPLATE,
        payload={
            "request_id": instance.pk,
            "request_label": f"REQ-{instance.created_at.year}-{instance.pk:04d}"
                             f" — {instance.company_name or '—'}",
            "old_status": old,
            "new_status": instance.status,
            "actor_name": (
                actor.get_full_name() or actor.username if actor else "system"
            ),
        },
        recipients=recipients,
        actor=actor,
        target=instance,
    )


# claude — same pre_save snapshot, plus inapp notifier on post_save
pre_save.connect(
    _capture_old_status,
    sender=RequestMain,
    dispatch_uid="notification.capture_old_status.RequestMain",
)
post_save.connect(
    _notify_inapp_on_request_status_change,
    sender=RequestMain,
    dispatch_uid="notification.inapp_on_request_status_change",
)
