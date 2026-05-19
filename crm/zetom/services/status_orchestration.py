"""Status-change orchestration for RequestMain.

Routes manual status changes from the change-view to the right underlying
service and decides whether a reason must be collected first.

Reason-required statuses (per product spec): inactive, cancelled, deleted.
For cancelled / deleted we delegate to the existing status_manager services.
_inactive_request lives here because status_manager has no helper for it
yet and is owned by another dev — the local function mirrors the pattern.
"""
from django.db import transaction

from crm.status_manager.models import StatusHistory
from crm.status_manager.services.status_service import (cancel_request,
                                                        delete_request)
from crm.status_manager.services.statuses import RequestStatus

REASON_REQUIRED_STATUSES = {
    RequestStatus.inactive,
    RequestStatus.cancelled,
    RequestStatus.deleted,
}


class ReasonRequired(Exception):
    """Signal to caller: this transition needs a reason; show the reason form."""


def _inactive_request(obj, user, reason):
    old_status = obj.status
    obj.status = RequestStatus.inactive
    obj.save()
    StatusHistory.objects.create(
        request=obj,
        old_status=old_status,
        new_status=RequestStatus.inactive,
        reason=reason,
        changed_by=user,
    )


@transaction.atomic
def apply_status_change(obj, user, new_status, reason=None):
    if new_status not in RequestStatus.values:
        raise ValueError("Invalid status")
    if new_status == obj.status:
        raise ValueError("Already in this status")

    if new_status in REASON_REQUIRED_STATUSES:
        if not reason:
            raise ReasonRequired()
        if new_status == RequestStatus.cancelled:
            cancel_request(obj, user, reason)
        elif new_status == RequestStatus.deleted:
            delete_request(obj, user, reason)
            obj.delete()
        else:
            _inactive_request(obj, user, reason)
        return

    old_status = obj.status
    obj.status = new_status
    obj.save()
    StatusHistory.objects.create(
        request=obj,
        old_status=old_status,
        new_status=new_status,
        reason="",
        changed_by=user,
    )
