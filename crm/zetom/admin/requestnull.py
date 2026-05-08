"""Validation Window admin — public form intake records.

Add view is disabled — RequestNull instances come exclusively from the
public site form (crm.zetom.views.email_template). Approve action
promotes a RequestNull into a RequestMain via approve_null_action.
"""
from django.contrib import admin
from django.db import transaction
from django.shortcuts import redirect
from unfold.decorators import action
from unfold.enums import ActionVariant

from crm.notification.services.notification_service import \
    send_notification_approve_null
from crm.zetom.forms import AddRequestFormNull
from crm.zetom.models import RequestNull
from crm.zetom.services.request_service import approve_null_action

from .base import BaseRequestAdmin


@admin.register(RequestNull)
class RequestNullAdmin(BaseRequestAdmin):
    form = AddRequestFormNull
    list_display = ("created_at", "updated_at", "company_name", "source")
    list_filter = ("source",)
    fields = (
        "first_name",
        "last_name",
        "phone",
        "email",
        "company_name",
        "message",
    )
    actions_detail = ["approve_action"]

    def has_add_permission(self, request):
        return False

    @action(description="Approve", variant=ActionVariant.SUCCESS, icon="")
    @transaction.atomic
    def approve_action(self, request, object_id):
        new_main_record = approve_null_action(object_id)
        send_notification_approve_null(new_main_record)
        return redirect("admin:zetom_requestmain_change", new_main_record.pk)
