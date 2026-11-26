"""Mandatory verification of an offer by a second person.

An Oferta may be emailed to the client only once someone other than the
person who asked for verification has approved it. Any change to the offer
after that puts it back to "not verified", so the client always gets the
version that was checked.

Who may verify (on top of "not the requester"):
  - admin (role or superuser),
  - head of one of the parent request's departments,
  - owner of the parent request,
  - anyone holding the `resolve_review` permission.
"""
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from crm.notification.models import Notification, NotificationKind
from crm.notification.services import inapp_service
from crm.notification.services.request_mail import document_code
from crm.users.utils import user_has_perm
from crm.zetom.models import Oferta
from crm.zetom.services.per_req_perms import (
    is_admin, is_dep_head_of_req, is_owner_of_req,
)

User = get_user_model()
V = Oferta.Verification

REQUEST_TEMPLATE = "notification/inapp/staff/review_requested.txt"
RESOLVED_TEMPLATE = "notification/inapp/staff/review_resolved.txt"
DECISIONS = (V.APPROVED, V.REJECTED)


def _may_review(user, oferta):
    """Role side of the rule, without the "not the requester" part."""
    if not (user and user.is_authenticated and user.is_active):
        return False
    if is_admin(user) or user_has_perm(user, "resolve_review"):
        return True
    req = oferta.from_main
    return bool(req and (is_dep_head_of_req(user, req) or is_owner_of_req(user, req)))


def can_verify(user, oferta):
    """May `user` approve/reject this offer right now?"""
    if oferta.verification_status != V.PENDING:
        return False
    if user.pk == oferta.verification_requested_by_id:
        return False
    return _may_review(user, oferta)


def reviewer_candidates(oferta, requester):
    """Active staff, other than the requester, who could verify the offer."""
    users = (
        User.objects.filter(is_active=True, is_staff=True)
        .exclude(pk=requester.pk)
        .select_related("profile__role")
        .order_by("first_name", "last_name", "username")
    )
    return [u for u in users if _may_review(u, oferta)]


def can_send(oferta):
    return oferta.verification_status == V.APPROVED


def send_blocked_reason(oferta):
    """Why the offer can't be sent yet, or None when it can."""
    if can_send(oferta):
        return None
    if oferta.verification_status == V.PENDING:
        return _("The offer is waiting for verification. It can be sent once another person approves it.")
    if oferta.verification_status == V.REJECTED:
        return _("The offer was rejected at verification. Fix it and request verification again.")
    return _("The offer must be verified by another person before it can be sent.")


def _label(oferta):
    return oferta.offer_number or document_code(oferta)


def _payload(oferta, **extra):
    req = oferta.from_main
    request_label = (
        f"REQ-{req.created_at.year}-{req.pk:04d} — {req.company_name or '—'}" if req
        else (oferta.company_name or "—")
    )
    return {
        "request_id": req.pk if req else None,
        "request_label": request_label,
        "document_label": str(_("Offer %(number)s") % {"number": _label(oferta)}),
        **extra,
    }


def _close_open_requests(oferta):
    """Clear the unread REVIEW_REQUEST notifications about this offer."""
    Notification.objects.filter(
        kind=NotificationKind.REVIEW_REQUEST,
        target_content_type=ContentType.objects.get_for_model(Oferta),
        target_object_id=oferta.pk,
        is_read=False,
    ).update(is_read=True, read_at=timezone.now())


@transaction.atomic
def request_verification(oferta, requester, reviewers, note=""):
    if oferta.verification_status in (V.PENDING, V.APPROVED):
        raise ValidationError(_("This offer is already waiting for verification or verified."))
    allowed = {u.pk for u in reviewer_candidates(oferta, requester)}
    reviewers = [u for u in reviewers if u.pk in allowed]
    if not reviewers:
        raise ValidationError(_("Pick at least one person who can verify the offer."))

    oferta.verification_status = V.PENDING
    oferta.verification_requested_by = requester
    oferta.verification_requested_at = timezone.now()
    oferta.verified_by = None
    oferta.verified_at = None
    oferta.verification_note = ""
    oferta.save(update_fields=[
        "verification_status", "verification_requested_by", "verification_requested_at",
        "verified_by", "verified_at", "verification_note",
    ])
    inapp_service.create_inapp(
        kind=NotificationKind.REVIEW_REQUEST,
        template_name=REQUEST_TEMPLATE,
        payload=_payload(
            oferta,
            requester_name=requester.get_full_name() or requester.username,
            note=note,
        ),
        recipients=reviewers,
        actor=requester,
        target=oferta,
    )
    return reviewers


@transaction.atomic
def resolve_verification(oferta, reviewer, decision, note=""):
    if decision not in DECISIONS:
        raise ValidationError(_("Unknown decision."))
    if not can_verify(reviewer, oferta):
        raise PermissionDenied(_("You can't verify this offer."))

    oferta.verification_status = decision
    oferta.verified_by = reviewer
    oferta.verified_at = timezone.now()
    oferta.verification_note = note
    oferta.save(update_fields=["verification_status", "verified_by", "verified_at", "verification_note"])

    _close_open_requests(oferta)
    requester = oferta.verification_requested_by
    if requester is not None:
        inapp_service.create_inapp(
            kind=NotificationKind.REVIEW_RESOLVED,
            template_name=RESOLVED_TEMPLATE,
            payload=_payload(
                oferta,
                resolver_name=reviewer.get_full_name() or reviewer.username,
                decision=decision,
                note=note,
            ),
            recipients=[requester],
            actor=reviewer,
            target=oferta,
        )


def invalidate(oferta):
    """The offer changed: a pending or granted approval no longer applies.

    Returns True when something was reset (so the caller can tell the user).
    """
    if oferta.verification_status not in (V.PENDING, V.APPROVED):
        return False
    oferta.verification_status = V.NONE
    oferta.verified_by = None
    oferta.verified_at = None
    oferta.verification_note = ""
    oferta.save(update_fields=["verification_status", "verified_by", "verified_at", "verification_note"])
    _close_open_requests(oferta)
    return True
