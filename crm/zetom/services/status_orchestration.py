"""Status-change orchestration for RequestMain.

The only status an employee/admin may set by hand is `cancelled` (requires
a reason). Everything else is computed automatically by status_manager
(see update_parent), and `deleted` goes only through the standard admin
delete flow (RequestMainAdmin.delete_view), not through here.
"""
from django.db import transaction

from crm.status_manager.services.status_service import (
    cancel_request, handle_child_change,
)
from crm.status_manager.services.statuses import RequestStatus, Status


class ReasonRequired(Exception):
    """Signal to caller: this transition needs a reason; show the reason form."""


def bump_new_to_in_progress(obj, old_status, change, user):
    """After a child-doc edit, auto-advance new -> in_progress.

    Only on edits (change=True), and only when the doc was `new` and stayed
    `new` (i.e. the form itself didn't move the status). Routed through the
    FSM service so the parent cascade and the client-email signal fire the
    same way as a manual transition.
    """
    if change and old_status == Status.new and obj.status == Status.new:
        handle_child_change(obj, Status.in_progress, reason=None, user=user)


@transaction.atomic
def apply_status_change(obj, user, new_status, reason=None):
    if new_status != RequestStatus.cancelled:
        raise ValueError("This status cannot be changed manually")
    if new_status == obj.status:
        raise ValueError("Already in this status")
    if not reason:
        raise ReasonRequired()
    cancel_request(obj, user, reason)
