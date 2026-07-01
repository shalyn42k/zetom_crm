# claude
"""Cancelled Validation Window leads (CancelledValidationRequest proxy on RequestNull).

Sibling of CancelledRequestAdmin, but the base model is RequestNull, so Restore
brings the lead back into the Validation Window (not the RequestMain change page).
"""
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from crm.status_manager.services.statuses import RequestStatus
from crm.users.utils import user_has_perm
from crm.zetom.models import (
    CancelledValidationRequest, DepartmentsVariants, RequestNull,
)
from crm.zetom.services.visibility import visible_requests_for

from .base import DepartmentsDisplayMixin


@admin.register(CancelledValidationRequest)
class CancelledValidationRequestAdmin(DepartmentsDisplayMixin, ModelAdmin):
    change_form_template = "admin/zetom/cancelledvalidationrequest/change_form.html"
    list_display = ("created_at", "company_name", "display_departments", "source")
    list_filter = ("source",)
    readonly_fields = (
        "first_name", "last_name", "phone", "departments", "assigned_to",
        "company_name", "company_nip", "email", "message", "source",
    )
    fields = readonly_fields

    # ---------- RBAC ----------

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_requests")

    def has_delete_permission(self, request, obj=None):
        return False

    # ---------- Queryset ----------

    def get_queryset(self, request):
        qs = RequestNull.objects.filter(status=RequestStatus.cancelled)
        return visible_requests_for(request.user, qs)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["show_save"] = False
        extra_context["show_save_and_continue"] = False
        extra_context["show_save_and_add_another"] = False
        extra_context["show_delete"] = False
        return super().changeform_view(request, object_id, form_url, extra_context)

    def render_change_form(self, request, context, *args, **kwargs):
        obj = context.get("original")
        if obj is not None:
            dept_labels = dict(DepartmentsVariants.choices)
            context["assigned_departments"] = [
                (code, dept_labels.get(code, code)) for code in (obj.departments or [])
            ]
            context["assigned_users_qs"] = obj.assigned_to.all()
            context["source_display"] = obj.get_source_display()
        profile = getattr(request.user, "profile", None)
        context["user_departments"] = profile.departments if profile else []
        return super().render_change_form(request, context, *args, **kwargs)

    # ---------- Custom URLs ----------

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<path:object_id>/restore/",
                self.admin_site.admin_view(self.restore_action),
                name="zetom_cancelledvalidationrequest_restore",
            ),
        ]
        return custom + urls

    # ---------- Restore ----------

    def restore_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_cancelledvalidationrequest_change", object_id)
        if not user_has_perm(request.user, "change_request_status"):
            return redirect("admin:zetom_cancelledvalidationrequest_change", object_id)
        qs = visible_requests_for(
            request.user,
            RequestNull.objects.filter(status=RequestStatus.cancelled),
        )
        obj = qs.filter(pk=object_id).first()
        if obj is None:
            return redirect("admin:zetom_cancelledvalidationrequest_changelist")
        obj.status = RequestStatus.active
        obj.save()
        return redirect("admin:zetom_requestnull_validate", object_id)
