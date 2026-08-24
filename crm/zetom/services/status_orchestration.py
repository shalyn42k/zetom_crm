"""Status-change orchestration for RequestMain.

The only status an employee/admin may set by hand is `cancelled` (requires
a reason). Everything else is computed automatically by status_manager
(see update_parent), and `deleted` goes only through the standard admin
delete flow (RequestMainAdmin.delete_view), not through here.
"""
from django.db import transaction

from crm.status_manager.services.status_service import (
    cancel_request, handle_child_change, update_parent,
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


# claude — system-driven transition, deliberately outside the manual FSM in
# status_manager.services.status_service.change_status: its transitions table
# only allows new->in_progress->waiting->done and done->{waiting,in_progress}.
# An Oferta sitting in `new` or `in_progress` when a Zlecenie is created from
# it can never reach `done` through that table, so routing this through
# change_status/handle_child_change would raise ValueError for most real
# offers. This assigns status=done directly instead, and cascades to the
# parent request via update_parent — same downstream effect as a normal FSM
# transition, without fabricating intermediate states the offer was never in
# and without loosening status_manager's transition table (which would also
# open up manual new->done from the UI — its author appears to have
# deliberately forbidden that).
#
# Intentionally NOT recorded in StatusHistory: that table is RequestMain-
# scoped (StatusHistory.request is a FK to RequestMain only, no FK to child
# docs) and its old_status/new_status columns are typed with RequestStatus,
# not the child-doc Status enum. change_status — the normal path for every
# other child-doc transition — writes no StatusHistory row either, so this
# doesn't skip an existing convention. Attaching a row to oferta.from_main
# would show up in the *parent request's* history as "new -> done", which
# never happened to the request itself — a false audit trail, worse than none.
@transaction.atomic
def close_oferta_on_zlecenie(oferta, user):
    """Auto-close an Oferta when a Zlecenie is created from it.

    No-op if the offer is already done, cancelled, or deleted — creating a
    Zlecenie from a closed offer shouldn't resurrect or double-close it.
    """
    if oferta.status in (Status.done, RequestStatus.cancelled, RequestStatus.deleted):
        return

    oferta.status = Status.done
    oferta.save(update_fields=["status"])

    if oferta.from_main_id:
        update_parent(oferta.from_main)


@transaction.atomic
def apply_status_change(obj, user, new_status, reason=None):
    if new_status != RequestStatus.cancelled:
        raise ValueError("This status cannot be changed manually")
    if new_status == obj.status:
        raise ValueError("Already in this status")
    if not reason:
        raise ReasonRequired()
    cancel_request(obj, user, reason)
