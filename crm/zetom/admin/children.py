"""Child documents — Oferta / Zlecenie / Wniosek admins.

Each shares the same shape: from_main is readonly (assigned by parent's
oferta_action / zlecenie_action / wniosek_action), and save_model is
delegated to save_child_with_status which respects the FSM transitions
defined in status_manager.
"""
from django.contrib import admin, messages

from crm.status_manager.services.status_service import save_child_with_status
from crm.zetom.forms import AddOferta, AddWniosek, AddZlecenie
from crm.zetom.models import Oferta, Wniosek, Zlecenie
from crm.zetom.services.status_orchestration import bump_new_to_in_progress

from .base import BaseRequestAdmin


@admin.register(Oferta)
class OfertaAdmin(BaseRequestAdmin):
    actions = []
    form = AddOferta
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
class ZlecenieAdmin(BaseRequestAdmin):
    actions = []
    form = AddZlecenie
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
class WniosekAdmin(BaseRequestAdmin):
    actions = []
    form = AddWniosek
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
