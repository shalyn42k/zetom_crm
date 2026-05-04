from itertools import chain

from django.db import transaction

from crm.status_manager.models import StatusHistory
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
        raise ValueError("Недопустимый переход статуса")

    child.status = new_status
    child.save()


def update_parent(parent):
    if parent.status in (RequestStatus.cancelled, RequestStatus.deleted):
        return
    children = list(
        chain(
            parent.oferta_set.all(),
            parent.zlecenie_set.all(),
            parent.wniosek_set.all(),
        )
    )

    if not children:
        parent.status = RequestStatus.inactive
        parent.save()
        return

    oferta = parent.oferta_set.exists()
    zlecenie = parent.zlecenie_set.exists()
    wniosek = parent.wniosek_set.exists()
    all_children = oferta and zlecenie and wniosek

    all_done = all(c.status == Status.done for c in children)

    if all_children and all_done:
        parent.status = RequestStatus.closed
    else:
        has_active = any(c.status in (Status.in_progress, Status.waiting) for c in children)
        if has_active:
            parent.status = RequestStatus.open
        else:
            parent.status = RequestStatus.active

    parent.save()


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


def delete_request(request_obj, user, reason):
    if request_obj.status == RequestStatus.deleted:
        raise ValueError("already deleted")
    old_status = request_obj.status
    request_obj.status = RequestStatus.deleted
    request_obj.save()
    StatusHistory.objects.create(
        request=request_obj,
        old_status=old_status,
        new_status=RequestStatus.deleted,
        reason=reason,
        changed_by=user,
    )
