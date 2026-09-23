"""Child documents — Oferta / Zlecenie / Wniosek admins.

Each shares the same shape: from_main is readonly (assigned by the
RequestMain-level approve_* actions in requestmain.py/request_service.py),
and save_model is delegated to save_child_with_status which respects the
FSM transitions defined in status_manager.

# claude — Fix-round: the per-document "create the next document" chain
# buttons (Oferta -> Zlecenie -> Wniosek, Task 11 — zlecenie_action on
# OfertaAdmin, wniosek_action on ZlecenieAdmin) were removed by request: a
# Zlecenie can have more than one Wniosek filed against it (and an Oferta
# more than one Zlecenie), so a button living ON one specific document,
# implying a 1:1 next-document link, didn't fit. The equivalent
# RequestMain-page buttons ("Create order"/"Create application" in
# requestmain.py, backed by request_service.py) were kept — they don't
# target one specific document, and still auto-close the prior stage the
# same way they always did (close_oferta_on_zlecenie /
# close_zlecenie_on_wniosek, now living in status_orchestration.py, called
# only from request_service.py). MarkDoneActionMixin below is the only
# manual close available on these forms themselves.
"""
from django.contrib import admin, messages
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from crm.status_manager.services.status_service import (
    delete_child_document, save_child_with_status, update_parent,
)
from crm.users.utils import user_has_perm
from crm.zetom.forms import AddOferta, AddWniosek, AddZlecenie
from crm.zetom.models import Oferta, Wniosek, Zlecenie
from crm.zetom.services.status_orchestration import (
    bump_new_to_in_progress, mark_child_done,
)

from .base import BaseRequestAdmin, ReasonForm


# claude — permission gate for the mark-done action below. Returns
# (obj, None) on success, or (None, HttpResponseForbidden) when the caller
# should bail out. 403 (not a redirect+message) matches the pattern already
# used for POST-action gates guarded by a role permission — see
# requestmain_mail._get_obj_for_mail / base._get_obj_for_step_note.
def _get_child_for_action(admin_instance, request, object_id, perm):
    if not user_has_perm(request.user, perm):
        return None, HttpResponseForbidden(
            _("You don't have permission for this action.")
        )
    obj = admin_instance.get_queryset(request).filter(pk=object_id).first()
    if obj is None:
        return None, HttpResponseForbidden(_("Not found."))
    return obj, None


# claude — child documents are hard-deleted (no soft-delete status to flip,
# unlike RequestMain), so the only place to capture "why" is at delete time.
# Mirrors RequestMainAdmin.delete_view (requestmain.py): single-object
# delete shows a reason form before actually deleting; bulk delete (list-
# page "Delete selected" action) has no per-object form to hang a reason
# on, so it falls back to a generic label, same as RequestMain's bulk path.
class ChildDeleteReasonMixin:
    def delete_view(self, request, object_id, extra_context=None):
        obj = self.get_object(request, object_id)
        if obj is None or not self.has_delete_permission(request, obj):
            return super().delete_view(request, object_id, extra_context)

        opts = self.model._meta
        if request.method == "POST":
            reason = (request.POST.get("reason") or "").strip()
            if reason:
                delete_child_document(obj, request.user, reason)
                messages.success(request, _("Document deleted."))
                return redirect(f"admin:{opts.app_label}_{opts.model_name}_changelist")
            messages.error(request, _("Reason is required."))

        form = ReasonForm()
        return render(
            request,
            "admin/zetom/shared/reason_form.html",
            {
                "form": form,
                "obj": obj,
                "cancel_url": reverse(
                    f"admin:{opts.app_label}_{opts.model_name}_change", args=[obj.pk]
                ),
                **self.admin_site.each_context(request),
            },
        )

    @transaction.atomic
    def delete_queryset(self, request, queryset):
        for obj in queryset:
            delete_child_document(obj, request.user, reason=_("Deleted via admin (bulk)"))


# claude — "Mark as done" button, shared by all three child-doc admins.
# Status editing is deliberately locked out of these forms entirely (see
# save_child_with_status: "status" isn't a form field). Oferta/Zlecenie can
# still get auto-closed from the RequestMain page (see the module
# docstring), but Wniosek never does — nothing is ever created from it —
# so this button is the only way to close one from its own change form.
class MarkDoneActionMixin:
    def get_urls(self):
        urls = super().get_urls()
        opts = self.model._meta
        custom = [
            path(
                "<path:object_id>/mark-done/",
                self.admin_site.admin_view(self.mark_done_action),
                name=f"{opts.app_label}_{opts.model_name}_mark_done",
            ),
        ]
        return custom + urls

    def mark_done_action(self, request, object_id):
        opts = self.model._meta
        change_url = f"admin:{opts.app_label}_{opts.model_name}_change"
        if request.method != "POST":
            return redirect(change_url, object_id)
        obj, denied = _get_child_for_action(self, request, object_id, "edit_requests")
        if denied is not None:
            return denied

        mark_child_done(obj, request.user)
        messages.success(request, _("Marked as done."))
        return redirect(change_url, object_id)


@admin.register(Oferta)
class OfertaAdmin(ChildDeleteReasonMixin, MarkDoneActionMixin, BaseRequestAdmin):
    actions = []
    form = AddOferta
    change_form_template = "admin/zetom/oferta/change_form.html"
    list_display = (
        "from_main", "created_at", "updated_at", "company_name",
        "display_departments", "assignees_display", "colored_status", "source",
    )
    list_filter = ("source",)
    readonly_fields = ("from_main",)
    fields = (
        "from_main",
        "phone",
        "departments",
        "assigned_to",
        "email",
        "company_name",
        "company_nip",
        "price",
        "notes",
        "source",
    )
    warn_unsaved_form = True

    def save_model(self, request, obj, form, change):
        # claude — снимаем статус до записи, чтобы поймать «был new»
        old_status = type(obj).objects.get(pk=obj.pk).status if change else None
        if save_child_with_status(request, obj, form, change, messages):
            super().save_model(request, obj, form, change)
            # claude — любая правка new-дока авто-двигает new -> in_progress
            bump_new_to_in_progress(obj, old_status, change, request.user)


@admin.register(Zlecenie)
class ZlecenieAdmin(ChildDeleteReasonMixin, MarkDoneActionMixin, BaseRequestAdmin):
    actions = []
    form = AddZlecenie
    change_form_template = "admin/zetom/zlecenie/change_form.html"
    list_display = (
        "from_main", "created_at", "updated_at", "company_name",
        "display_departments", "assignees_display", "colored_status", "source",
    )
    list_filter = ("source",)
    readonly_fields = ("from_main",)
    fields = (
        "from_main",
        "deadline",
        "phone",
        "departments",
        "assigned_to",
        "email",
        "company_name",
        "company_nip",
        "price",
        "notes",
        "source",
    )
    warn_unsaved_form = True

    def save_model(self, request, obj, form, change):
        # claude — снимаем статус до записи, чтобы поймать «был new»
        old_status = type(obj).objects.get(pk=obj.pk).status if change else None
        if save_child_with_status(request, obj, form, change, messages):
            super().save_model(request, obj, form, change)
            # claude — любая правка new-дока авто-двигает new -> in_progress
            bump_new_to_in_progress(obj, old_status, change, request.user)


@admin.register(Wniosek)
class WniosekAdmin(ChildDeleteReasonMixin, MarkDoneActionMixin, BaseRequestAdmin):
    actions = []
    form = AddWniosek
    change_form_template = "admin/zetom/wniosek/change_form.html"
    list_display = (
        "from_main", "created_at", "updated_at", "company_name",
        "display_departments", "assignees_display", "colored_status", "source",
    )
    list_filter = ("source",)
    readonly_fields = ("from_main",)
    fields = (
        "from_main",
        "application_number",
        "phone",
        "departments",
        "assigned_to",
        "email",
        "company_name",
        "company_nip",
        "notes",
        "source",
    )
    warn_unsaved_form = True

    def save_model(self, request, obj, form, change):
        # claude — снимаем статус до записи, чтобы поймать «был new»
        old_status = type(obj).objects.get(pk=obj.pk).status if change else None
        if save_child_with_status(request, obj, form, change, messages):
            super().save_model(request, obj, form, change)
            # claude — любая правка new-дока авто-двигает new -> in_progress
            bump_new_to_in_progress(obj, old_status, change, request.user)
