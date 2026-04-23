# Django imports
from django import forms
from django.contrib import admin, messages
from django.contrib.admin.models import LogEntry
from django.db import transaction
from django.shortcuts import redirect

# Unfold imports
from unfold.admin import ModelAdmin
from unfold.decorators import action
from unfold.enums import ActionVariant

# Notification app imports
from notification.services.notification_service import send_notification_approve_null

# Users app imports
from users.utils import user_has_perm

# Zetom app imports
from zetom.forms import AddOferta, AddRequestFormMain, AddRequestFormNull
from zetom.models import Oferta, RequestMain, RequestNull
from zetom.services.request_service import approve_null_action, approve_oferta_action


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



# LogEntryAdmin
@admin.register(LogEntry)
class LogEntryAdmin(ModelAdmin):
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



# RequestNullAdmin
@admin.register(RequestNull)
class RequestNullAdmin(BaseRequestAdmin):
    form = AddRequestFormNull
    list_display = ("created_at", "phone", "company_name", "company_nip", "email")
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



# RequestMainAdmin
@admin.register(RequestMain)
class RequestMainAdmin(BaseRequestAdmin):
    form = AddRequestFormMain
    list_display = ("created_at", "company_name")
    fields = (
        "full_name",
        "phone",
        "company_name",
        "company_nip",
        "email",
        "address",
        "notes",
    )
    actions_detail = ["oferta_action", "zlecenie_action"]
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



# OfertaAdmin
@admin.register(Oferta)
class OfertaAdmin(BaseRequestAdmin):
    form = AddOferta
    list_display = ("created_at", "company_name")
    readonly_fields = ("from_main",)
    fields = ("from_main", "phone", "email", "company_name", "company_nip", "price")
    warn_unsaved_form = True
