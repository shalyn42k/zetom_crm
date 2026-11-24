"""POST endpoint for "Request review" on the RequestMain change form.

Plug-in as a mixin onto `RequestMainAdmin`. The action creates an inapp
notification with kind=REVIEW_REQUEST aimed at users picked in the
modal: default-cascade owners → dep_heads → admins (filtered by per-Req
hierarchy) PLUS extra recipients the sender ticked from the picker.

Per-Req rules + sender→target eligibility live in
`crm.zetom.services.per_req_perms`. Cascade + candidate pool live in
`crm.notification.services.recipients`.
"""
# Django imports
from django import forms
from django.contrib import messages
from django.http import HttpResponseForbidden
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from django.urls import path
from django.utils.translation import gettext_lazy as _

from crm.notification.models import NotificationKind
from crm.notification.services import inapp_service
from crm.notification.services.recipients import review_candidates_for
from crm.users.utils import user_has_perm
from crm.zetom.models import RequestMain
from crm.zetom.services.per_req_perms import (
    is_owner_of_req, request_review_eligible,
)
from crm.zetom.services.visibility import visible_requests_for

# claude
User = get_user_model()


# claude
class ReviewRequestForm(forms.Form):
    """Note-only form. recipient_ids читаются вручную из request.POST
    через `getlist` — checkbox-набор не ложится в Django-форму чисто
    без явных choices, а choices здесь зависят от Req и роли юзера.
    """
    note = forms.CharField(required=False, max_length=1000, widget=forms.Textarea)


REVIEW_TEMPLATE = "notification/inapp/staff/review_requested.txt"


# claude
class RequestReviewMixin:
    """Adds /<id>/request-review/ to RequestMainAdmin."""

    def get_urls(self):
        urls = super().get_urls()
        view = self.admin_site.admin_view
        custom = [
            path(
                "<path:object_id>/request-review/",
                view(self.request_review_action),
                name="zetom_requestmain_request_review",
            ),
        ]
        return custom + urls

    def _get_req_for_review_action(self, request, object_id):
        if not user_has_perm(request.user, "request_review"):
            return None, HttpResponseForbidden(
                _("You don't have permission for this action.")
            )

        qs = visible_requests_for(request.user, RequestMain.objects.all())
        obj = qs.filter(pk=object_id).first()
        if obj is None:
            return None, HttpResponseForbidden(_("Request not found."))
        return obj, None

    def request_review_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)

        obj, forbidden = self._get_req_for_review_action(request, object_id)
        if forbidden is not None:
            return forbidden

        form = ReviewRequestForm(request.POST)
        if not form.is_valid():
            messages.error(request, _("Could not submit review request."))
            return redirect("admin:zetom_requestmain_change", object_id)

        # claude — пересчитываем default/extras заново на сервере, чтобы
        # не доверять клиенту в том, кто read-only. Owners-из-default
        # уходят в финальный список всегда (если eligible для sender'а).
        sender = request.user
        default, _extras = review_candidates_for(obj, sender)
        forced_ids = {
            u.pk for u in default if is_owner_of_req(u, obj)
        }

        # extras + non-owner default'ы, которые юзер не снял
        selected_raw = request.POST.getlist("recipient_ids")
        try:
            selected_ids = {int(x) for x in selected_raw if x}
        except ValueError:
            messages.error(request, _("Invalid recipient selection."))
            return redirect("admin:zetom_requestmain_change", object_id)

        final_ids = forced_ids | selected_ids
        final_ids.discard(sender.pk)
        if not final_ids:
            messages.error(request, _("Pick at least one recipient."))
            return redirect("admin:zetom_requestmain_change", object_id)

        # Defence-in-depth: каждого получателя проверяем правилом eligibility.
        recipients = [
            u for u in User.objects.filter(pk__in=final_ids, is_active=True)
            if request_review_eligible(sender, u, obj)
        ]
        if not recipients:
            messages.error(request, _("No reviewers available to notify."))
            return redirect("admin:zetom_requestmain_change", object_id)

        inapp_service.create_inapp(
            kind=NotificationKind.REVIEW_REQUEST,
            template_name=REVIEW_TEMPLATE,
            payload={
                "request_id": obj.pk,
                "request_label": (
                    f"REQ-{obj.created_at.year}-{obj.pk:04d}"
                    f" — {obj.company_name or '—'}"
                ),
                "document_label": "",
                "requester_name": (
                    sender.get_full_name() or sender.username
                ),
                "note": form.cleaned_data["note"],
            },
            recipients=recipients,
            actor=sender,
            target=obj,
        )
        messages.success(request, _("Review request sent."))
        return redirect("admin:zetom_requestmain_change", object_id)
