"""POST endpoint for "Request review" on the RequestMain change form.

Plug-in as a mixin onto `RequestMainAdmin`. The action creates an inapp
notification with kind=REVIEW_REQUEST aimed at dep_heads of the Req's
departments (admin fallback). Recipient resolution is delegated to
`crm.notification.services.recipients.dep_heads_or_admins`.
"""
# Django imports
from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import path
from django.utils.translation import gettext_lazy as _

# Local imports
from crm.notification.models import NotificationKind
from crm.notification.services import inapp_service
from crm.notification.services.recipients import dep_heads_or_admins
from crm.zetom.models import RequestMain


# claude
class ReviewRequestForm(forms.Form):
    """Just a free-text comment, optional. Empty `note` is fine — the inapp
    template falls back to "(no comment provided)"."""
    note = forms.CharField(
        required=False,
        max_length=1000,
        widget=forms.Textarea,
    )


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

    def request_review_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)
        obj = get_object_or_404(RequestMain, pk=object_id)

        form = ReviewRequestForm(request.POST)
        if not form.is_valid():
            messages.error(request, _("Could not submit review request."))
            return redirect("admin:zetom_requestmain_change", object_id)

        recipients = dep_heads_or_admins(obj)
        # Defence-in-depth: if the resolver returns nothing (no dep_head AND
        # no admin in the system) — surface that to the user instead of
        # silently dropping the request.
        if not recipients:
            messages.error(request, _("No reviewers available to notify."))
            return redirect("admin:zetom_requestmain_change", object_id)

        # The author of the request shouldn't see their own ping in the
        # unread inbox — drop them from recipients if they happen to qualify
        # as dep_head/admin themselves.
        recipients = [u for u in recipients if u.pk != request.user.pk]
        if not recipients:
            messages.error(request, _("Only you qualify as a reviewer — request not sent."))
            return redirect("admin:zetom_requestmain_change", object_id)

        requester = request.user
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
                    requester.get_full_name() or requester.username
                ),
                "note": form.cleaned_data["note"],
            },
            recipients=recipients,
            actor=requester,
            target=obj,
        )
        messages.success(request, _("Review request sent."))
        return redirect("admin:zetom_requestmain_change", object_id)
