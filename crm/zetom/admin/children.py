"""Child documents — Oferta / Zlecenie / Wniosek admins.

Each shares the same shape: from_main is readonly (assigned by parent's
oferta_action / zlecenie_action / wniosek_action), and save_model is
delegated to save_child_with_status which respects the FSM transitions
defined in status_manager.

# claude — also carries the "create the next document" actions for the
# Oferta -> Zlecenie -> Wniosek soft chain (Task 11): zlecenie_action on
# OfertaAdmin, wniosek_action on ZlecenieAdmin. Same shape as the
# RequestMain -> child actions in requestmain.py, one link deeper.
"""
from django.contrib import admin, messages
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import path
from django.utils.translation import gettext_lazy as _

from crm.status_manager.services.status_service import (
    save_child_with_status, update_parent,
)
from crm.users.utils import user_has_perm
from crm.zetom.forms import AddOferta, AddWniosek, AddZlecenie
from crm.zetom.models import Oferta, Wniosek, Zlecenie
from crm.zetom.services.status_orchestration import (
    bump_new_to_in_progress, close_oferta_on_zlecenie,
)

from .base import BaseRequestAdmin


# claude — permission gate for the create-next-document actions below.
# Returns (obj, None) on success, or (None, HttpResponseForbidden) when the
# caller should bail out. 403 (not a redirect+message) matches the pattern
# already used for POST-action gates guarded by a role permission — see
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


# claude — creates the next chain document (Zlecenie from Oferta, Wniosek
# from Zlecenie). Inherits the contact snapshot from the parent document
# (not RequestMain) and always copies from_main — a document without it
# silently disappears from _step_note_targets and from visibility filtering.
def _create_next_document(model, parent, **extra):
    child = model.objects.create(
        from_main=parent.from_main,
        first_name=parent.first_name,
        last_name=parent.last_name,
        phone=parent.phone,
        email=parent.email,
        company_name=parent.company_name,
        company_nip=parent.company_nip,
        departments=list(parent.departments or []),
        source=parent.source,
        **extra,
    )
    child.assigned_to.set(parent.assigned_to.all())
    return child


@admin.register(Oferta)
class OfertaAdmin(BaseRequestAdmin):
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

    # claude — "Create order from this offer" button (Task 11).
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<path:object_id>/zlecenie/",
                self.admin_site.admin_view(self.zlecenie_action),
                name="zetom_oferta_zlecenie_action",
            ),
        ]
        return custom + urls

    def zlecenie_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_oferta_change", object_id)
        obj, denied = _get_child_for_action(self, request, object_id, "edit_requests")
        if denied is not None:
            return denied

        zlecenie = _create_next_document(Zlecenie, obj, from_oferta=obj, price=0)
        # claude — creating an order from an offer closes the offer, even
        # though it may be `new`/`in_progress` and can't reach `done` through
        # the manual FSM (see close_oferta_on_zlecenie for why).
        close_oferta_on_zlecenie(obj, request.user)
        messages.success(request, _("Order created."))
        return redirect("admin:zetom_zlecenie_change", zlecenie.pk)


@admin.register(Zlecenie)
class ZlecenieAdmin(BaseRequestAdmin):
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

    # claude — "Create application from this order" button (Task 11). No
    # auto-close here: unlike Oferta -> Zlecenie, a Wniosek being created
    # from a Zlecenie does not change the order's status — deliberate, per
    # spec §3.2 (no symmetric auto-close rule for this hop).
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<path:object_id>/wniosek/",
                self.admin_site.admin_view(self.wniosek_action),
                name="zetom_zlecenie_wniosek_action",
            ),
        ]
        return custom + urls

    def wniosek_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_zlecenie_change", object_id)
        obj, denied = _get_child_for_action(self, request, object_id, "edit_requests")
        if denied is not None:
            return denied

        wniosek = _create_next_document(Wniosek, obj, from_zlecenie=obj)
        if obj.from_main_id:
            update_parent(obj.from_main)
        messages.success(request, _("Application created."))
        return redirect("admin:zetom_wniosek_change", wniosek.pk)


@admin.register(Wniosek)
class WniosekAdmin(BaseRequestAdmin):
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
