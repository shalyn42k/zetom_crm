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
from django.db.models.signals import m2m_changed, post_save, pre_save

# Local imports
from crm.notification.models import NotificationKind
from crm.notification.services import inapp_service, request_mail
from crm.notification.services.recipients import default_recipients
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
    # claude — set by the "send document to client" action: the finished
    # document is being emailed right now, a second "it's in progress" mail
    # in the same second would only confuse the client.
    if getattr(instance, "_skip_in_progress_mail", False):
        return
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
    recipients = default_recipients(instance)
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


# claude — specialist added to RequestMain.assigned_to → inapp ASSIGNMENT for
# each newly added user (matrix row #8). The actor (set as instance._actor by
# the admin view before .add()/.set()) is skipped — nobody needs to be told
# they assigned themselves. Respects NotificationPreference.inapp_assignment
# through create_inapp.
REQUEST_ASSIGNED_TEMPLATE = "notification/inapp/staff/request_assigned.txt"


def _notify_inapp_on_assignment(sender, instance, action, pk_set, **kwargs):
    if action != "post_add" or not pk_set or not isinstance(instance, RequestMain):
        return
    from django.contrib.auth import get_user_model

    actor = getattr(instance, "_actor", None)
    added = get_user_model().objects.filter(pk__in=pk_set, is_active=True)
    if actor is not None:
        added = added.exclude(pk=actor.pk)
    inapp_service.create_inapp(
        kind=NotificationKind.ASSIGNMENT,
        template_name=REQUEST_ASSIGNED_TEMPLATE,
        payload={
            "request_id": instance.pk,
            "request_label": f"REQ-{instance.created_at.year}-{instance.pk:04d}"
                             f" — {instance.company_name or '—'}",
            "actor_name": (actor.get_full_name() or actor.username) if actor else "system",
        },
        recipients=list(added),
        actor=actor,
        target=instance,
    )


m2m_changed.connect(
    _notify_inapp_on_assignment,
    sender=RequestMain.assigned_to.through,
    dispatch_uid="notification.inapp_on_assignment",
)
