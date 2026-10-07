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
# claude — Fix-round: only called from request_service.py's
# approve_zlecenie_action (the "Create order" button on the RequestMain
# page) now, not from a per-document chain button — that one (and its
# Zlecenie->Wniosek counterpart) was removed by explicit request, since a
# single Oferta/Zlecenie can have more than one Zlecenie/Wniosek filed
# against it and a button living ON one specific Oferta implied a 1:1 link
# that doesn't hold. The RequestMain-page path was kept as asked — it
# doesn't target one specific linked document, it just closes out
# everything not already done when the next stage is approved from there.
#
# Intentionally NOT recorded in StatusHistory: that table is RequestMain-
# scoped (StatusHistory.request is a FK to RequestMain only, no FK to child
# docs) and its old_status/new_status columns are typed with RequestStatus,
# not the child-doc Status enum. change_status — the normal path for every
# other child-doc transition — writes no StatusHistory row either, so this
# doesn't skip an existing convention.
@transaction.atomic
def close_oferta_on_zlecenie(oferta, user):
    """Auto-close an Oferta when a Zlecenie is approved for its request.

    No-op if the offer is already done, cancelled, or deleted.
    """
    if oferta.status in (Status.done, RequestStatus.cancelled, RequestStatus.deleted):
        return

    oferta.status = Status.done
    oferta.save(update_fields=["status"])

    if oferta.from_main_id:
        update_parent(oferta.from_main)


# claude — same contract as close_oferta_on_zlecenie above, one hop later:
# only called from request_service.py's approve_wniosek_action now.
@transaction.atomic
def close_zlecenie_on_wniosek(zlecenie, user):
    """Auto-close a Zlecenie when a Wniosek is approved for its request.

    No-op if the order is already done, cancelled, or deleted.
    """
    if zlecenie.status in (Status.done, RequestStatus.cancelled, RequestStatus.deleted):
        return

    zlecenie.status = Status.done
    zlecenie.save(update_fields=["status"])

    if zlecenie.from_main_id:
        update_parent(zlecenie.from_main)


# claude — "Mark as done" button on Oferta/Zlecenie/Wniosek change forms.
# Status editing is deliberately locked out of those admin forms entirely
# (see ChildSaveModelTests — "status" isn't a form field). This is the only
# way to close a document that isn't covered by the request-level
# close_*_on_* hooks above — most notably Wniosek, which nothing is ever
# created from, so it never gets an auto-close hook at all.
@transaction.atomic
def mark_child_done(obj, user):
    """Manually mark an Oferta/Zlecenie/Wniosek as done.

    No-op if already done, cancelled, or deleted.
    """
    if obj.status in (Status.done, RequestStatus.cancelled, RequestStatus.deleted):
        return

    obj.status = Status.done
    obj.save(update_fields=["status"])

    if obj.from_main_id:
        update_parent(obj.from_main)


@transaction.atomic
def apply_status_change(obj, user, new_status, reason=None):
    if new_status != RequestStatus.cancelled:
        raise ValueError("This status cannot be changed manually")
    if new_status == obj.status:
        raise ValueError("Already in this status")
    if not reason:
        raise ReasonRequired()
    cancel_request(obj, user, reason)
