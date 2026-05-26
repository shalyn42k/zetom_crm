# claude
"""Validation Window — custom admin view that replaces the single
"Approve" button on RequestNull.

Mounts at  admin/zetom/requestnull/<pk>/validate/  via `get_urls` on
RequestNullAdmin. Renders the three-zone form (snapshot · link to client ·
assignment) described in handoff/Zetom Validation Window. On POST runs an
atomic transaction:

    1. Create or link a Client (depending on the validator's choice).
    2. Promote RequestNull -> RequestMain (existing approve_null_action).
    3. Apply Client data on top of the new RequestMain when a Client was
       chosen / created (so the new RequestMain reflects the canonical
       Client record, not the raw form data).
    4. Set departments / assigned_to / owners on the RequestMain.
    5. Redirect to the RequestMain change page.

NOTE — partial behaviour (see UI notices on the page):
    * Owner filter "by department" is NOT live — owners list shows every
      qualified user; the chosen-vs-filtered relationship is enforced on
      submit (clean_owners). HTMX refresh is a follow-up.
    * Drag-reorder of "primary owner" is NOT implemented — the first owner
      (by pk) is treated as primary.
    * The ad-hoc client search box is decorative — only auto-proposed
      candidates can be linked right now.
    * No FK from RequestMain to Client exists yet; "linking" copies the
      Client's data onto the new RequestMain but does not persist a
      relation. Tracked separately.
"""
from __future__ import annotations

from django import forms
from django.contrib import messages
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from crm.clients.models import Client
from crm.notification.services.notification_service import (
    send_notification_approve_null,
)
from crm.status_manager.services.status_service import cancel_request
from crm.status_manager.services.statuses import RequestStatus
from crm.zetom.models import DepartmentsVariants, RequestMain, RequestNull
from crm.zetom.services.duplicate_matcher import find_candidates
from crm.zetom.services.request_service import approve_null_action

LINK_NEW = "new"
LINK_UNLINKED = "unlinked"


# ---------------------------------------------------------------------------
# Form
# ---------------------------------------------------------------------------

class ValidationWindowForm(forms.Form):
    link_choice = forms.CharField(required=True)

    # new-client inline form (used only when link_choice == "new")
    new_first_name = forms.CharField(required=False, max_length=100)
    new_last_name = forms.CharField(required=False, max_length=100)
    new_company_name = forms.CharField(required=False, max_length=255)
    new_company_nip = forms.CharField(required=False, max_length=20)
    new_phone = forms.CharField(required=False, max_length=32)
    new_email = forms.EmailField(required=False)

    departments = forms.MultipleChoiceField(
        choices=DepartmentsVariants.choices,
        required=True,
    )
    owners = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),  # populated in __init__
        required=True,
    )

    def __init__(self, *args, candidate_ids=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._candidate_ids = set(candidate_ids or [])
        # All active users — the eligibility-by-department check happens in
        # clean_owners. We can't restrict the queryset here because we
        # don't know which departments the validator picks until cleaning.
        self.fields["owners"].queryset = User.objects.filter(is_active=True)

    def clean_link_choice(self):
        choice = (self.cleaned_data.get("link_choice") or "").strip()
        if choice in (LINK_NEW, LINK_UNLINKED):
            return choice
        if choice.startswith("link:"):
            try:
                pk = int(choice.split(":", 1)[1])
            except ValueError:
                raise forms.ValidationError(_("Bad link choice."))
            if pk not in self._candidate_ids:
                raise forms.ValidationError(_("Selected client is not in the candidate list."))
            return choice
        raise forms.ValidationError(_("Please pick how to link this request."))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("link_choice") == LINK_NEW:
            # Require at minimum a phone or email so the new Client is searchable
            if not (cleaned.get("new_phone") or cleaned.get("new_email")):
                self.add_error(
                    "new_phone",
                    _("Provide at least a phone or email for the new client."),
                )

        # Enforce owners ⊆ users-with-any-of-selected-departments
        departments = cleaned.get("departments") or []
        owners = cleaned.get("owners")
        if departments and owners:
            invalid = [
                u for u in owners
                if not set(getattr(u.profile, "departments", []) or []) & set(departments)
            ]
            if invalid:
                names = ", ".join(u.get_username() for u in invalid)
                self.add_error(
                    "owners",
                    _("These users have no overlap with the selected departments: %(names)s")
                    % {"names": names},
                )
        return cleaned


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------

def _snapshot_fields(rn: RequestNull) -> list[dict]:
    """Build the read-only Snapshot card rows + inline validity hints.

    Hints are non-blocking commentary except `err`, which is reserved for
    actually missing required data.
    """
    rows = []
    rows.append({
        "key": "first_name",
        "label": _("First name"),
        "value": rn.first_name,
        "hint": ("ok", _("present")) if rn.first_name else ("err", _("required, missing")),
    })
    rows.append({
        "key": "last_name",
        "label": _("Last name"),
        "value": rn.last_name,
        "hint": ("ok", _("present")) if rn.last_name else ("err", _("required, missing")),
    })

    phone_str = str(rn.phone) if rn.phone else ""
    rows.append({
        "key": "phone",
        "label": _("Phone"),
        "value": phone_str,
        "hint": ("ok", _("E.164 format")) if phone_str else ("err", _("required, missing")),
        "mono": True,
    })

    email = rn.email or ""
    rows.append({
        "key": "email",
        "label": _("Email"),
        "value": email,
        "hint": ("ok", _("valid")) if "@" in email else ("err", _("required, invalid")),
        "mono": True,
    })

    rows.append({
        "key": "company_name",
        "label": _("Company"),
        "value": rn.company_name,
        "hint": ("info", _("optional · acceptable empty")) if not rn.company_name
                else ("ok", _("present")),
    })

    rows.append({
        "key": "message",
        "label": _("Message"),
        "value": rn.message,
        "long": True,
        "hint": ("info", _("free text from the website form")) if rn.message else
                ("info", _("no message provided")),
    })
    return rows


def _banner_state(rn: RequestNull, candidates) -> dict:
    """Pick banner colour + title based on what the matcher returned."""
    required_ok = bool(rn.first_name and rn.last_name and rn.phone and rn.email)
    if not required_ok:
        return {
            "kind": "warn",
            "title": _("Required fields missing — review before approving"),
            "sub": _("Approve is disabled until the snapshot has all required fields."),
        }
    if not candidates:
        return {
            "kind": "info",
            "title": _("No duplicate clients found · email domain looks fine"),
            "sub": _("Proceed by creating a new client from the snapshot data."),
        }
    if len(candidates) == 1 and candidates[0].is_strong:
        return {
            "kind": "ok",
            "title": _("One strong duplicate found · all required fields valid"),
            "sub": _("Recommended action: link to the proposed client."),
        }
    return {
        "kind": "warn",
        "title": _("%(n)d possible duplicates · pick the closest match") % {"n": len(candidates)},
        "sub": _("Several candidates match — review the badges before linking."),
    }


def _initial_link_choice(candidates) -> str:
    if candidates and candidates[0].is_strong:
        return f"link:{candidates[0].client.pk}"
    return LINK_NEW


def _eligible_users():
    return (
        User.objects
        .filter(is_active=True)
        .select_related("profile")
        .order_by("first_name", "last_name", "username")
    )


@transaction.atomic
def _do_approve(rn: RequestNull, cleaned: dict):
    choice = cleaned["link_choice"]
    client = None
    if choice == LINK_NEW:
        client = Client.objects.create(
            first_name=cleaned.get("new_first_name") or rn.first_name,
            last_name=cleaned.get("new_last_name") or rn.last_name,
            company_name=cleaned.get("new_company_name") or rn.company_name,
            company_nip=cleaned.get("new_company_nip") or None,
            phone=cleaned.get("new_phone") or rn.phone,
            email=cleaned.get("new_email") or rn.email,
        )
    elif choice.startswith("link:"):
        client = Client.objects.filter(pk=int(choice.split(":", 1)[1])).first()

    # 1) Promote RequestNull -> RequestMain using the existing service.
    new_main: RequestMain = approve_null_action(rn.pk)

    # 2) When a Client is involved, prefer its canonical values over the
    #    raw RequestNull values (the validator just confirmed they match).
    if client is not None:
        for fld, val in (
            ("first_name", client.first_name),
            ("last_name", client.last_name),
            ("company_name", client.company_name),
            ("company_nip", client.company_nip),
            ("phone", client.phone),
            ("email", client.email),
        ):
            if val:
                setattr(new_main, fld, val)

    new_main.departments = list(cleaned["departments"])
    new_main.save()

    owners = list(cleaned["owners"])
    new_main.assigned_to.set(owners)
    new_main.owners.set(owners)

    return new_main


# ---------------------------------------------------------------------------
# Mixin to register the URL on RequestNullAdmin
# ---------------------------------------------------------------------------

class ValidationWindowMixin:
    """Adds /<id>/validate/ to RequestNullAdmin."""

    def get_urls(self):
        urls = super().get_urls()
        view = self.admin_site.admin_view
        custom = [
            path(
                "<int:object_id>/validate/",
                view(self.validation_window_view),
                name="zetom_requestnull_validate",
            ),
        ]
        return custom + urls

    def validation_window_view(self, request, object_id):
        rn = get_object_or_404(RequestNull, pk=object_id)

        # Discard-as-spam fires from the same screen via a hidden field.
        # We promote RequestNull -> RequestMain so the entry remains
        # auditable, then immediately transition it to `cancelled` with
        # a system-supplied reason (cancellation is reason-required —
        # see status_orchestration.REASON_REQUIRED_STATUSES). The result
        # shows up under CancelledRequest, not under deleted.
        if request.method == "POST" and request.POST.get("__action") == "discard":
            with transaction.atomic():
                new_main = approve_null_action(rn.pk)
                cancel_request(
                    new_main,
                    request.user,
                    reason=_("Discarded as spam from the Validation Window."),
                )
            messages.success(request, _("Request discarded as spam (moved to Cancelled)."))
            return redirect("admin:zetom_cancelledrequest_changelist")

        candidates = find_candidates(rn)
        candidate_ids = [c.client.pk for c in candidates]
        snapshot = _snapshot_fields(rn)
        banner = _banner_state(rn, candidates)
        eligible_users = _eligible_users()

        if request.method == "POST":
            form = ValidationWindowForm(request.POST, candidate_ids=candidate_ids)
            if form.is_valid():
                new_main = _do_approve(rn, form.cleaned_data)
                try:
                    send_notification_approve_null(new_main)
                except Exception:  # noqa: BLE001 — notification must not block approve
                    pass
                messages.success(request, _("Request approved and promoted."))
                return redirect("admin:zetom_requestmain_change", new_main.pk)
        else:
            form = ValidationWindowForm(
                initial={
                    "link_choice": _initial_link_choice(candidates),
                    "new_first_name": rn.first_name or "",
                    "new_last_name": rn.last_name or "",
                    "new_phone": str(rn.phone) if rn.phone else "",
                    "new_email": rn.email or "",
                    "new_company_name": rn.company_name or "",
                },
                candidate_ids=candidate_ids,
            )

        # Pull selection state out of bound/unbound form into plain
        # collections so the template doesn't have to wrestle with
        # form.<field>.value() returning None on GET.
        selected_link = form["link_choice"].value() or _initial_link_choice(candidates)
        selected_depts = set(form["departments"].value() or [])
        owner_raw = form["owners"].value() or []
        selected_owner_ids = {str(v) for v in owner_raw}

        context = {
            **self.admin_site.each_context(request),
            "title": _("Validation Window — RequestNull #%(id)d") % {"id": rn.pk},
            "request_null": rn,
            "snapshot": snapshot,
            "banner": banner,
            "candidates": candidates,
            "departments_choices": DepartmentsVariants.choices,
            "eligible_users": eligible_users,
            "form": form,
            "selected_link": selected_link,
            "selected_depts": selected_depts,
            "selected_owner_ids": selected_owner_ids,
            "LINK_NEW": LINK_NEW,
            "LINK_UNLINKED": LINK_UNLINKED,
            "cancel_url": reverse("admin:zetom_requestnull_changelist"),
            "opts": self.model._meta,
            "has_view_permission": True,
        }
        return render(request, "admin/zetom/requestnull/validate.html", context)
