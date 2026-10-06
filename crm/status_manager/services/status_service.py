from itertools import chain

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from crm.status_manager.models import ChildDocumentDeletion, StatusHistory
from crm.status_manager.services.statuses import RequestStatus, Status


def handle_child_change(child, new_status, reason, user):
    with transaction.atomic():
        change_status(child, new_status, reason, user)
        parent = child.from_main
        if parent:
            update_parent(parent)


def change_status(child, new_status, reason, user):
    if new_status is None:
        return

    current_status = child.status

    transitions = {
        Status.new: [Status.in_progress],
        Status.in_progress: [Status.waiting],
        Status.waiting: [Status.done],
        Status.done: [Status.waiting, Status.in_progress],
    }

    allowed = transitions.get(current_status, [])

    if new_status == current_status:
        return

    if new_status not in allowed:
        raise ValueError(_("Invalid status transition."))

    child.status = new_status
    child.save()


def update_parent(parent):
    if parent.status in (RequestStatus.cancelled, RequestStatus.deleted):
        return

    old_status = parent.status
    children = list(
        chain(
            parent.oferta_set.all(),
            parent.zlecenie_set.all(),
            parent.wniosek_set.all(),
        )
    )

    if not children:
        new_status = RequestStatus.active
    else:
        oferta = parent.oferta_set.exists()
        zlecenie = parent.zlecenie_set.exists()
        wniosek = parent.wniosek_set.exists()
        all_children = oferta and zlecenie and wniosek

        all_done = all(c.status == Status.done for c in children)

        if all_children and all_done:
            new_status = RequestStatus.closed
        else:
            has_active = any(c.status in (Status.in_progress, Status.waiting) for c in children)
            new_status = RequestStatus.open if has_active else RequestStatus.active

    parent.status = new_status
    parent.save()

    # claude — update_parent drives every active<->open<->closed transition
    # (fired from child create/status-change signals), but used to never
    # log to the dedicated StatusHistory audit model — only the manual
    # Cancel action did. The RequestMain "Historia" panel renders
    # status_history, so it showed nothing for the vast majority of real
    # status changes. changed_by=None since this path has no request user
    # (signals, bulk orchestration) — it's a system-driven transition.
    if new_status != old_status:
        StatusHistory.objects.create(
            request=parent,
            old_status=old_status,
            new_status=new_status,
            reason=_("Automatic transition based on child document statuses."),
            changed_by=None,
        )


def save_child_with_status(request, obj, form, change, messages_module):
    new_status = form.cleaned_data.get("status")
    if change:
        obj.status = type(obj).objects.get(pk=obj.pk).status
    try:
        handle_child_change(obj, new_status, reason=None, user=request.user)
    except ValueError as e:
        messages_module.error(request, str(e))
        return False
    return True


def cancel_request(request_obj, user, reason):
    if request_obj.status in (RequestStatus.cancelled, RequestStatus.deleted):
        raise ValueError("already cancelled/deleted")
    old_status = request_obj.status
    request_obj.status = RequestStatus.cancelled
    request_obj.save()
    StatusHistory.objects.create(
        request=request_obj,
        old_status=old_status,
        new_status=RequestStatus.cancelled,
        reason=reason,
        changed_by=user,
    )


def delete_child_document(obj, user, reason):
    """Hard-delete an Oferta/Zlecenie/Wniosek, logging why.

    Unlike RequestMain, child documents have no soft-delete status to flip —
    the row is actually removed, so the reason is captured on
    ChildDocumentDeletion (the only record left once obj is gone) rather
    than on the object itself.
    """
    with transaction.atomic():
        parent = obj.from_main
        ChildDocumentDeletion.objects.create(
            document_type=type(obj).__name__,
            document_repr=str(obj),
            from_main=parent,
            reason=reason,
            deleted_by=user,
        )
        obj.delete()
        if parent:
            update_parent(parent)


def delete_request(request_obj, user, reason):
    if request_obj.status == RequestStatus.deleted:
        raise ValueError("already deleted")
    old_status = request_obj.status
    request_obj.status = RequestStatus.deleted
    request_obj.save()
    request_obj.delete() 
    StatusHistory.objects.create(
        request=request_obj,
        old_status=old_status,
        new_status=RequestStatus.deleted,
        reason=reason,
        changed_by=user,
    )
