"""Trash admin (DeletedRequest proxy on RequestMain).

Read-only view of soft-deleted requests with custom Restore /
Hard-delete buttons in the submit bar (rendered in the trash
change_form template via admin URLs registered below).
"""
from django.contrib import admin, messages
from django.db import transaction
from django.shortcuts import redirect
from django.urls import path
from unfold.admin import ModelAdmin

from crm.status_manager.models import StatusHistory
from crm.status_manager.services.statuses import RequestStatus
from crm.users.utils import user_has_perm
from crm.zetom.models import (DeletedRequest, DepartmentsVariants, Oferta,
                              RequestMain, Wniosek, Zlecenie)

from .base import DepartmentsDisplayMixin


@admin.register(DeletedRequest)
class DeletedRequestAdmin(DepartmentsDisplayMixin, ModelAdmin):
    change_form_template = "admin/zetom/deletedrequest/change_form.html"
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

    # ---------- RBAC ----------

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # Allow opening the change view so the Restore action works.
        return user_has_perm(request.user, "view_requests")

    def has_delete_permission(self, request, obj=None):
        return False

    # ---------- Queryset / submit bar / context ----------

    def get_queryset(self, request):
        return RequestMain.deleted_objects.all()

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
            # SOFT_DELETE_CASCADE soft-deletes children too — read via
            # all_objects so we still see what was attached at delete time.
            context["ofertas"] = (
                Oferta.all_objects.filter(from_main=obj).order_by("-created_at")
            )
            context["zlecenia"] = (
                Zlecenie.all_objects.filter(from_main=obj).order_by("-created_at")
            )
            context["wnioski"] = (
                Wniosek.all_objects.filter(from_main=obj).order_by("-created_at")
            )
            dept_labels = dict(DepartmentsVariants.choices)
            context["assigned_departments"] = [
                (code, dept_labels.get(code, code)) for code in (obj.departments or [])
            ]
            context["assigned_users_qs"] = obj.assigned_to.all()
            context["source_display"] = obj.get_source_display()
        profile = getattr(request.user, "profile", None)
        context["user_department"] = profile.department if profile else None
        return super().render_change_form(request, context, *args, **kwargs)

    # ---------- Custom URLs ----------

    def get_urls(self):
        urls = super().get_urls()
        view = self.admin_site.admin_view
        custom = [
            path(
                "<path:object_id>/restore/",
                view(self.restore_action),
                name="zetom_deletedrequest_restore",
            ),
            path(
                "<path:object_id>/hard-delete/",
                view(self.hard_delete_action),
                name="zetom_deletedrequest_hard_delete",
            ),
        ]
        return custom + urls

    # ---------- Restore / hard-delete actions ----------

    @transaction.atomic
    def restore_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_deletedrequest_change", object_id)
        obj = RequestMain.deleted_objects.get(pk=object_id)
        obj.undelete()
        obj.status = RequestStatus.active
        obj.save()
        StatusHistory.objects.create(
            request=obj,
            old_status=RequestStatus.deleted,
            new_status=RequestStatus.active,
            reason="Restored from trash",
            changed_by=request.user,
        )
        messages.success(request, "Request restored.")
        return redirect("admin:zetom_requestmain_change", object_id)

    @transaction.atomic
    def hard_delete_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_deletedrequest_change", object_id)
        from safedelete.config import HARD_DELETE
        obj = RequestMain.deleted_objects.get(pk=object_id)
        obj.delete(force_policy=HARD_DELETE)
        messages.success(request, "Request permanently deleted.")
        return redirect("admin:zetom_deletedrequest_changelist")
