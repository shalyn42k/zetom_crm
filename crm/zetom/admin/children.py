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
from django.utils import timezone
from django.utils.translation import gettext_lazy as _, gettext_noop
from unfold.admin import StackedInline
from unfold.widgets import UnfoldAdminTextInputWidget

from crm.status_manager.services.status_service import (
    delete_child_document, save_child_with_status, update_parent,
)
from crm.users.utils import user_has_perm
from crm.zetom.forms import AddOferta, AddWniosek, AddZlecenie
from crm.zetom.models import Oferta, OfertaItem, Wniosek, Zlecenie
from crm.zetom.services.status_orchestration import (
    bump_new_to_in_progress, mark_child_done,
)

from .base import BaseRequestAdmin, ReasonForm
from .document_window import DocumentWindowMixin

# claude — document window fieldsets: the template's own fields first, the
# client snapshot collapsed underneath.
# Departments, assignees and source are inherited from the request and are
# no longer edited on the document (they still exist on the model).
CLIENT_FIELDSET = (
    _("Client data on the document"),
    {
        "classes": ("collapse",),
        # one field per row: the left column of the document window is too
        # narrow for pairs (the right-hand inputs spilled out of the card)
        "fields": ("first_name", "last_name", "company_name", "company_nip", "email", "phone"),
    },
)


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
                # claude — see RequestMainAdmin.cancel_view's identical fix:
                # without opts/original, Unfold's header falls back to a
                # generic "Welcome {username}" instead of the normal
                # breadcrumb trail every other page shows.
                "opts": opts,
                "original": obj,
                "title": _("Delete document"),
                **self.admin_site.each_context(request),
            },
        )

    @transaction.atomic
    def delete_queryset(self, request, queryset):
        for obj in queryset:
            delete_child_document(
                obj, request.user, reason=gettext_noop("Deleted via admin (bulk)")
            )


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


# claude — Unfold-styled input with the browser's own calendar picker
# (type="date" posts YYYY-MM-DD; DateField accepts it via input_formats).
class CalendarDateWidget(UnfoldAdminTextInputWidget):
    input_type = "date"

    def format_value(self, value):
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d")
        return value or None


# claude — lines of the offer table. Permissions follow the project's RBAC,
# not Django's own model perms (which this project never populates — the
# inline would otherwise be hidden from everyone but superusers).
class OfertaItemInline(StackedInline):
    # Stacked, not tabular: the left column of the document window is too
    # narrow for six columns side by side.
    model = OfertaItem
    extra = 0
    # No manual "order" field: lines keep the order they were added in.
    fields = ("name", "details", "norm", "quantity", "unit_price")
    placeholders = {
        "name": "np. Maszyna wytrzymałościowa : DSI NIEMCY typ HOZ 4000/250",
        "details": "np. Kierunek działania siły: rozciąganie, zakres :500kN.",
        "norm": "np. wg Norma PN-EN ISO 7500-1; 2018",
    }

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if field is not None:
            if db_field.name == "details":
                field.widget.attrs["rows"] = 2
            if db_field.name in self.placeholders:
                field.widget.attrs["placeholder"] = self.placeholders[db_field.name]
        return field
    verbose_name = _("Offer item")
    verbose_name_plural = _("Offer items")

    def has_view_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_requests")

    def has_add_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_requests")

    def has_change_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_requests")

    def has_delete_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_requests")


@admin.register(Oferta)
class OfertaAdmin(DocumentWindowMixin, ChildDeleteReasonMixin, MarkDoneActionMixin, BaseRequestAdmin):
    actions = []
    form = AddOferta
    can_mark_done = True
    list_display = (
        "from_main", "created_at", "updated_at", "company_name",
        "display_departments", "assignees_display", "colored_status", "source",
    )
    list_filter = ("source",)
    readonly_fields = ("from_main",)
    inlines = [OfertaItemInline]
    # claude — only what changes from offer to offer is on view; the number
    # (set automatically) and the standard terms that are the same on almost
    # every offer sit in a collapsed "More options".
    fieldsets = (
        (_("Offer"), {"fields": ("offer_date", "subject", "inquiry_channel", "inquiry_date")}),
        (_("Price and deadline"), {"fields": ("extra_costs", "completion_term")}),
        (_("More options"), {
            "classes": ("collapse",),
            "fields": ("offer_number", "vat_rate", "place_of_work", "confirmation_document", "payment_terms"),
        }),
        CLIENT_FIELDSET,
        (_("Internal note"), {"classes": ("collapse",), "fields": ("notes",)}),
    )
    # dates from a calendar (native date picker)
    date_fields = ("offer_date", "inquiry_date")
    placeholders = {
        "offer_number": _("set automatically when empty"),
        "completion_term": "np. listopad 2025 r.",
        "extra_costs": "0,00",
    }

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if field is None:
            return field
        if db_field.name in self.date_fields:
            field.widget = CalendarDateWidget()
            field.input_formats = ["%Y-%m-%d", "%d.%m.%Y"]
        if db_field.name in self.placeholders:
            field.widget.attrs["placeholder"] = self.placeholders[db_field.name]
        return field

    # claude — after the item lines are saved: offer number in the sample's
    # LTO/<no>/<YYYY-MM> shape when left empty, today's date when none, and
    # `price` = net total so mails / lists that read it stay right.
    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        updates = {"price": obj.net_total}
        if not obj.offer_date:
            updates["offer_date"] = timezone.localdate()
        if not obj.offer_number:
            when = updates.get("offer_date") or obj.offer_date
            updates["offer_number"] = f"LTO/{obj.pk}/{when:%Y-%m}"
        type(obj).objects.filter(pk=obj.pk).update(**updates)
        for k, v in updates.items():
            setattr(obj, k, v)
    warn_unsaved_form = True

    def save_model(self, request, obj, form, change):
        # claude — снимаем статус до записи, чтобы поймать «был new»
        old_status = type(obj).objects.get(pk=obj.pk).status if change else None
        if save_child_with_status(request, obj, form, change, messages):
            super().save_model(request, obj, form, change)
            # claude — любая правка new-дока авто-двигает new -> in_progress
            bump_new_to_in_progress(obj, old_status, change, request.user)


# claude — no MarkDoneActionMixin here by explicit request: unlike Oferta/
# Wniosek, Zlecenie should only ever reach `done` via the auto-close chain
# (creating a Wniosek from the parent RequestMain closes every not-yet-done
# Zlecenie on it — see close_zlecenie_on_wniosek). A request that never
# needs a Wniosek keeps its Zlecenie open rather than getting force-closed
# by hand from this form.
@admin.register(Zlecenie)
class ZlecenieAdmin(DocumentWindowMixin, ChildDeleteReasonMixin, BaseRequestAdmin):
    actions = []
    form = AddZlecenie

    # claude — deadline from a calendar, same as the offer dates
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if field is not None and db_field.name == "deadline":
            field.widget = CalendarDateWidget()
            field.input_formats = ["%Y-%m-%d", "%d.%m.%Y"]
        return field
    list_display = (
        "from_main", "created_at", "updated_at", "company_name",
        "display_departments", "assignees_display", "colored_status", "source",
    )
    list_filter = ("source",)
    readonly_fields = ("from_main",)
    fieldsets = (
        (_("Order"), {"fields": (("deadline", "price"), "notes")}),
        CLIENT_FIELDSET,
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
class WniosekAdmin(DocumentWindowMixin, ChildDeleteReasonMixin, MarkDoneActionMixin, BaseRequestAdmin):
    actions = []
    form = AddWniosek
    can_mark_done = True
    list_display = (
        "from_main", "created_at", "updated_at", "company_name",
        "display_departments", "assignees_display", "colored_status", "source",
    )
    list_filter = ("source",)
    readonly_fields = ("from_main",)
    fieldsets = (
        (_("Application"), {"fields": ("application_number", "notes")}),
        CLIENT_FIELDSET,
    )
    warn_unsaved_form = True

    def save_model(self, request, obj, form, change):
        # claude — снимаем статус до записи, чтобы поймать «был new»
        old_status = type(obj).objects.get(pk=obj.pk).status if change else None
        if save_child_with_status(request, obj, form, change, messages):
            super().save_model(request, obj, form, change)
            # claude — любая правка new-дока авто-двигает new -> in_progress
            bump_new_to_in_progress(obj, old_status, change, request.user)
