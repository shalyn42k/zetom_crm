"""Offer verification in the document window (OfertaAdmin only).

Two POST endpoints — request verification, resolve it — plus the hooks the
shared DocumentWindowMixin calls: extra window context, a reason that blocks
"Send to client", and resetting the approval when the offer is edited.
Rules live in crm.zetom.services.oferta_verification.
"""
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from crm.zetom.models import Oferta
from crm.zetom.services import oferta_verification as verification

User = get_user_model()
V = Oferta.Verification


class OfertaVerificationMixin:
    def get_urls(self):
        wrap = self.admin_site.admin_view
        return [
            path("<path:object_id>/verification/request/", wrap(self.request_verification_action),
                 name="zetom_oferta_request_verification"),
            path("<path:object_id>/verification/resolve/", wrap(self.resolve_verification_action),
                 name="zetom_oferta_resolve_verification"),
        ] + super().get_urls()

    # ---- actions ----------------------------------------------------------

    def request_verification_action(self, request, object_id):
        if request.method != "POST":
            return redirect(self._change_url(object_id))
        obj, allowed = self._get_doc(request, object_id, change=True)
        if not allowed:
            return HttpResponseForbidden(_("You don't have permission for this action."))
        try:
            ids = {int(x) for x in request.POST.getlist("reviewer_ids") if x}
        except ValueError:
            ids = set()
        reviewers = list(User.objects.filter(pk__in=ids, is_active=True))
        try:
            sent_to = verification.request_verification(
                obj, request.user, reviewers, note=(request.POST.get("note") or "").strip()[:1000],
            )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect(self._change_url(obj))
        names = ", ".join(u.get_full_name() or u.username for u in sent_to)
        messages.success(request, _("Verification requested from: %(names)s") % {"names": names})
        return redirect(self._change_url(obj))

    def resolve_verification_action(self, request, object_id):
        if request.method != "POST":
            return redirect(self._change_url(object_id))
        obj, allowed = self._get_doc(request, object_id)
        if not allowed:
            return HttpResponseForbidden(_("You don't have permission for this action."))
        decision = request.POST.get("decision", "")
        try:
            verification.resolve_verification(
                obj, request.user, decision, note=(request.POST.get("note") or "").strip()[:1000],
            )
        except PermissionDenied as exc:
            return HttpResponseForbidden(str(exc))
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect(self._change_url(obj))
        if decision == V.APPROVED:
            messages.success(request, _("Offer verified. It can now be sent to the client."))
        else:
            messages.warning(request, _("Offer rejected at verification. The author has been notified."))
        return redirect(self._change_url(obj))

    # ---- hooks used by DocumentWindowMixin --------------------------------

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if not change:
            return
        edited = bool(form.changed_data) or any(fs.has_changed() for fs in formsets)
        if edited and verification.invalidate(form.instance):
            messages.warning(request, _("The offer changed after verification — it needs to be verified again."))

    def send_blocked_reason(self, obj):
        return verification.send_blocked_reason(obj)

    def extra_doc_window_context(self, request, obj):
        user = request.user
        can_change = self.has_change_permission(request, obj)
        status = obj.verification_status
        can_request = can_change and status in (V.NONE, V.REJECTED)
        return {
            "verification": {
                "status": status,
                "label": obj.get_verification_status_display(),
                "requested_by": obj.verification_requested_by,
                "requested_at": obj.verification_requested_at,
                "verified_by": obj.verified_by,
                "verified_at": obj.verified_at,
                "note": obj.verification_note,
                "can_request": can_request,
                "candidates": verification.reviewer_candidates(obj, user) if can_request else [],
                "request_url": reverse("admin:zetom_oferta_request_verification", args=[obj.pk]),
                "can_resolve": verification.can_verify(user, obj),
                "resolve_url": reverse("admin:zetom_oferta_resolve_verification", args=[obj.pk]),
                "is_own_request": status == V.PENDING and obj.verification_requested_by_id == user.pk,
            },
        }
