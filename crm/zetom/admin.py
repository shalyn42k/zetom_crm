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
from crm.notification.services.notification_service import send_notification_approve_null

# Users app imports
from crm.users.models import Role, UserProfile

# Zetom app imports
from crm.zetom.forms import AddOferta, AddRequestFormMain, AddRequestFormNull
from crm.zetom.models import Oferta, RequestMain, RequestNull
from crm.zetom.services.request_service import approve_null_action, approve_oferta_action

# Other imports


# AI-generated (unknown, legacy): LogEntryAdmin — read-only viewer for django admin log
@admin.register(LogEntry)
class LogEntryAdmin(ModelAdmin):  # Используем ModelAdmin от Unfold для красоты
    list_display = ("action_time", "user", "content_type", "object_repr", "action_flag")
    list_filter = ("action_flag", "content_type", "user")
    search_fields = ("object_repr", "change_message")

    # Запрещаем всё, кроме просмотра
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RequestNull)
class RequestNullAdmin(ModelAdmin):
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
class RequestMainAdmin(ModelAdmin):
    form = AddRequestFormMain
    list_display = ("created_at", "updated_at", "company_name")
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
    actions_detail = ["request_info_action", "oferta_action", "zlecenie_action"]
    warn_unsaved_form = True

    @action(description="Oferta", icon="assignment", url_path="oferta")
    def oferta_action(self, request, object_id):
        oferta = approve_oferta_action(object_id)
        messages.info(request, f"Redirecting to Oferta: {object_id}")
        return redirect("admin:zetom_oferta_change", oferta.pk)

    @action(description="Zlecenie", icon="assignment", url_path="zlecenie_action")
    def zlecenie_action(self, request, object_id):
        self.message_user(request, "no zlecenie :(")
        return redirect("admin:zetom_requestmain_change", object_id)

    # AI-edited (claude-opus-4-7, 2026-04-21): simplified to render static design mockup only
    @action(description="Request Info", icon="article", url_path="request-info")
    def request_info_action(self, request, object_id):
        return render(
            request,
            "admin/zetom/requestmain/request_info.html",
            self.admin_site.each_context(request),
        )


@admin.register(Oferta)
class OfertaAdmin(ModelAdmin):
    form = AddOferta
    list_display = ("created_at", "updated_at", "company_name")
    readonly_fields = ("from_main",)
    fields = ("from_main", "phone","department", "email", "company_name", "company_nip", "price", "notes")
    warn_unsaved_form = True
