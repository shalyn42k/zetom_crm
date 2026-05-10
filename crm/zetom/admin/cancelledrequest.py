from django.contrib import admin
from django.shortcuts import redirect
from unfold.admin import ModelAdmin

from crm.status_manager.models import StatusHistory
from crm.status_manager.services.statuses import RequestStatus
from crm.users.utils import user_has_perm
from crm.zetom.models import CancelledRequest, DepartmentsVariants, RequestMain

from .base import DepartmentsDisplayMixin


@admin.register(CancelledRequest)
class CancelledRequestAdmin(DepartmentsDisplayMixin, ModelAdmin):
    change_form_template = "admin/zetom/cancelledrequest/change_form.html"
    list_display = ("created_at", "company_name", "display_departments", "source")
    list_filter = ("source",)
    readonly_fields = (
        "status", "first_name", "last_name", "phone", "departments", "assigned_to",
        "company_name", "company_nip", "email", "address", "message", "source",
    )
    fields = (
        "status", "first_name", "last_name", "phone", "departments", "assigned_to",
        "company_name", "company_nip", "email", "address", "message", "source",
    )

    def get_queryset(self, request):
        return RequestMain.objects.filter(status=RequestStatus.cancelled)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_requests")

    def has_delete_permission(self, request, obj=None):
        return False

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["show_save"] = False
        extra_context["show_save_and_continue"] = False
        extra_context["show_save_and_add_another"] = False
        extra_context["show_delete"] = False
        return super().changeform_view(request, object_id, form_url, extra_context)

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom = [
            path(
                "<path:object_id>/restore/",
                self.admin_site.admin_view(self.restore_action),
                name="zetom_cancelledrequest_restore",
            ),
        ]
        return custom + urls

    def restore_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_cancelledrequest_change", object_id)
        obj = RequestMain.objects.get(pk=object_id)
        old_status = obj.status
        obj.status = RequestStatus.active
        obj.save()
        StatusHistory.objects.create(
            request=obj,
            old_status=old_status,
            new_status=RequestStatus.active,
            reason="Restored from cancelled",
            changed_by=request.user,
        )
        return redirect("admin:zetom_requestmain_change", object_id)