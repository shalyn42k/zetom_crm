# Django imports
from django import forms
from django.contrib import admin, messages
from django.contrib.admin.models import LogEntry
from django.db import transaction
from django.shortcuts import redirect, render
# Unfold imports
from unfold.admin import ModelAdmin
from unfold.decorators import action
from unfold.enums import ActionVariant

# Notification app imports
from crm.notification.services.notification_service import \
    send_notification_approve_null
# Users app imports
from crm.users.utils import user_has_perm
# Zetom app imports
from crm.zetom.forms import (AddOferta, AddRequestFormMain, AddRequestFormNull,
                             AddWniosek, AddZlecenie)
from crm.zetom.models import (Oferta, RequestMain, RequestNull, Wniosek,
                              Zlecenie)
from crm.zetom.services.request_service import (approve_null_action,
                                                approve_oferta_action,
                                                approve_wniosek_action,
                                                approve_zlecenie_action)
from crm.zetom.services.services import (handle_child_change,
                                         save_child_with_status)

# Other imports


class BaseRequestAdmin(ModelAdmin):
    # RBAC для запросов (общие разрешения для RequestNull, RequestMain, Oferta)
    def has_view_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_requests")

    def has_add_permission(self, request):
        return user_has_perm(request.user, "edit_requests")

    def has_change_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_requests")

    def has_delete_permission(self, request, obj=None):
        return user_has_perm(request.user, "delete_requests")



# AI-generated (unknown, legacy): LogEntryAdmin — read-only viewer for django admin log
@admin.register(LogEntry)
class LogEntryAdmin(ModelAdmin):  # Используем ModelAdmin от Unfold для красоты
    list_display = ("action_time", "user", "content_type", "object_repr", "action_flag")
    list_filter = ("action_flag", "content_type", "user")
    search_fields = ("object_repr", "change_message")

    # RBAC
    def has_view_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_admin_panel")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RequestNull)
class RequestNullAdmin(BaseRequestAdmin):
    form = AddRequestFormNull
    list_display = ("created_at", "updated_at", "company_name")
    actions_detail = ["approve_action"]

    @action(
        description="Approve",
        variant=ActionVariant.SUCCESS,
        icon="",
    )
    @transaction.atomic
    def approve_action(self, request, object_id):
        new_main_record = approve_null_action(object_id)
        send_notification_approve_null(new_main_record)

        return redirect("admin:zetom_requestmain_change", new_main_record.pk)


@admin.register(RequestMain)
class RequestMainAdmin(BaseRequestAdmin):
    form = AddRequestFormMain
    list_display = ("created_at", "updated_at", "company_name", "status", "is_archived")
    fields = (
        "full_name",
        "phone",
        "department",
        "company_name",
        "company_nip",
        "email",
        "address",
        "message",
    )
    actions_detail = ["request_info_action", "oferta_action", "zlecenie_action", "wniosek_action"]
    warn_unsaved_form = True

    @action(description="Oferta", icon="assignment", url_path="oferta")
    def oferta_action(self, request, object_id):
        oferta = approve_oferta_action(object_id)
        messages.info(request, f"Redirecting to Oferta: {object_id}")
        return redirect("admin:zetom_oferta_change", oferta.pk)

    @action(description="Zlecenie", icon="assignment", url_path="zlecenie")
    def zlecenie_action(self, request, object_id):
        zlecenie = approve_zlecenie_action(object_id)
        messages.info(request, f"Redirecting to Zlecenie: {object_id}")
        return redirect("admin:zetom_zlecenie_change", zlecenie.pk)

    @action(description="Wniosek", icon="assignment", url_path="wniosek")
    def wniosek_action(self, request, object_id):
        wniosek = approve_wniosek_action(object_id)
        messages.info(request, f"Redirecting to Wniosek: {object_id}")
        return redirect("admin:zetom_wniosek_change", wniosek.pk)


    # AI-edited (claude-opus-4-7, 2026-04-21): simplified to render static design mockup only
    @action(description="Request Info", icon="article", url_path="request-info")
    def request_info_action(self, request, object_id):
        return render(
            request,
            "admin/zetom/requestmain/request_info.html",
            self.admin_site.each_context(request),
        )


# AI-suggested (claude-opus-4-7, 2026-04-23): save_model во всех трёх админках ниже делегирует в save_child_with_status — паттерн предложен Claude, код написал пользователь.
@admin.register(Oferta)
class OfertaAdmin(BaseRequestAdmin):
    form = AddOferta
    list_display = ("created_at", "updated_at", "company_name", "status")
    readonly_fields = ("from_main",)
    fields = ("from_main", "phone", "status", "department", "email", "company_name", "company_nip", "price", "notes")
    warn_unsaved_form = True

    def save_model(self, request, obj, form, change):
         if save_child_with_status(request, obj, form, change, messages):
            super().save_model(request, obj, form, change)
 
    
@admin.register(Zlecenie)
class ZlecenieAdmin(BaseRequestAdmin):
    form = AddZlecenie
    list_display = ("created_at", "updated_at", "company_name", "status")
    readonly_fields = ("from_main",)
    fields = ("from_main","deadline", "phone", "status", "department", "email", "company_name", "company_nip", "price", "notes")
    warn_unsaved_form = True

    def save_model(self, request, obj, form, change):
         if save_child_with_status(request, obj, form, change, messages):
            super().save_model(request, obj, form, change)
    

@admin.register(Wniosek)
class WniosekAdmin(BaseRequestAdmin):
    form = AddWniosek
    list_display = ("created_at", "updated_at", "company_name", "status")
    readonly_fields = ("from_main",)
    fields = ("from_main","application_number", "phone", "status", "department", "email", "company_name", "company_nip", "notes",)
    warn_unsaved_form = True

    def save_model(self, request, obj, form, change):
         if save_child_with_status(request, obj, form, change, messages):
            super().save_model(request, obj, form, change)


