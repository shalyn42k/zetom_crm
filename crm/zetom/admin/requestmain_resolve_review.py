"""POST endpoint + helpers for "Resolve review" on the RequestMain change form.

Симметрично RequestReviewMixin: dep_head/admin отвечает на запрос ревью,
который пришёл от спеца. Получатель REVIEW_RESOLVED — автор последней
REVIEW_REQUEST на этом Req (берём из `Notification.actor`, чтобы не
заводить отдельную модель ReviewRequest на альфу).
"""
# Django imports
from django import forms
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import redirect
from django.urls import path
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

# Local imports
from crm.notification.models import Notification, NotificationKind
from crm.notification.services import inapp_service
from crm.zetom.models import RequestMain
from crm.zetom.services.per_req_perms import can_resolve_review

REVIEW_RESOLVED_TEMPLATE = "notification/inapp/staff/review_resolved.txt"

DECISION_APPROVED = "approved"
DECISION_REJECTED = "rejected"
DECISION_CHOICES = [
    (DECISION_APPROVED, _("Approved")),
    (DECISION_REJECTED, _("Rejected")),
]


# claude
class ResolveReviewForm(forms.Form):
    decision = forms.ChoiceField(choices=DECISION_CHOICES, required=True)
    note = forms.CharField(
        required=False,
        max_length=1000,
        widget=forms.Textarea,
    )


# claude
def latest_open_review(req):
    """Return the latest REVIEW_REQUEST Notification for this Req that has
    not yet been resolved, or None.

    "Open" = exists REVIEW_REQUEST whose created_at is greater than the
    latest REVIEW_RESOLVED (or there's no REVIEW_RESOLVED at all). The
    inapp log is per-recipient, but timestamps within one event align,
    so this comparison is enough without a dedicated ReviewRequest model.
    """
    ct = ContentType.objects.get_for_model(RequestMain)
    base = Notification.objects.filter(
        target_content_type=ct,
        target_object_id=req.pk,
    )
    last_req = (
        base.filter(kind=NotificationKind.REVIEW_REQUEST)
        .order_by("-created_at")
        .first()
    )
    if last_req is None:
        return None
    last_resolved_at = (
        base.filter(kind=NotificationKind.REVIEW_RESOLVED)
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    if last_resolved_at is not None and last_resolved_at >= last_req.created_at:
        return None
    return last_req


# claude
class RequestResolveReviewMixin:
    """Adds /<id>/resolve-review/ to RequestMainAdmin."""

    def get_urls(self):
        urls = super().get_urls()
        view = self.admin_site.admin_view
        custom = [
            path(
                "<path:object_id>/resolve-review/",
                view(self.resolve_review_action),
                name="zetom_requestmain_resolve_review",
            ),
        ]
        return custom + urls

    def resolve_review_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)

        # claude — owner-of-Req тоже может резолвить (даже если у него
        # роль specialist), поэтому perm-чек теперь контекстный. Грузим
        # Req первым, чтобы было что передать в can_resolve_review.
        obj = RequestMain.objects.filter(pk=object_id).first()
        if obj is None:
            messages.error(request, _("Request not found."))
            return redirect("admin:zetom_requestmain_changelist")

        if not can_resolve_review(request.user, obj):
            messages.error(request, _("You don't have permission for this action."))
            return redirect("admin:zetom_requestmain_change", object_id)

        form = ResolveReviewForm(request.POST)
        if not form.is_valid():
            messages.error(request, _("Could not resolve review."))
            return redirect("admin:zetom_requestmain_change", object_id)

        open_review = latest_open_review(obj)
        if open_review is None:
            messages.error(request, _("No open review to resolve."))
            return redirect("admin:zetom_requestmain_change", object_id)
        requester = open_review.actor
        if requester is None:
            # Автор пропал (удалили юзера) — без получателя слать некому.
            messages.error(request, _("Original review requester is no longer available."))
            return redirect("admin:zetom_requestmain_change", object_id)

        resolver = request.user
        decision = form.cleaned_data["decision"]
        inapp_service.create_inapp(
            kind=NotificationKind.REVIEW_RESOLVED,
            template_name=REVIEW_RESOLVED_TEMPLATE,
            payload={
                "request_id": obj.pk,
                "request_label": (
                    f"REQ-{obj.created_at.year}-{obj.pk:04d}"
                    f" — {obj.company_name or '—'}"
                ),
                "resolver_name": resolver.get_full_name() or resolver.username,
                "decision": decision,
                "note": form.cleaned_data["note"],
            },
            recipients=[requester],
            actor=resolver,
            target=obj,
        )

        # claude — единственное место, где REVIEW_REQUEST у этого dep_head
        # помечается как прочитанный (mark_read-view это намеренно не делает).
        # Бьём только по этому Req — другие открытые ревью у того же dep_head
        # на других заявках продолжают висеть непрочитанными.
        ct = ContentType.objects.get_for_model(RequestMain)
        Notification.objects.filter(
            recipient=resolver,
            kind=NotificationKind.REVIEW_REQUEST,
            target_content_type=ct,
            target_object_id=obj.pk,
            is_read=False,
        ).update(is_read=True, read_at=timezone.now())

        messages.success(request, _("Review resolved."))
        return redirect("admin:zetom_requestmain_change", object_id)
