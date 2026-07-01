# claude
"""Trash for soft-deleted Validation Window leads (DeletedValidationRequest
proxy on RequestNull).

Sibling of DeletedRequestAdmin, but the base model is RequestNull, so Restore
brings the lead back into the **Validation Window** (not the RequestMain change
page). This is the type-aware half of the trash: a record that was a RequestMain
restores to RequestMain; a record that was a Validation Window lead restores to
the Validation Window.
"""
from django.contrib import admin, messages
from django.db import transaction
from django.shortcuts import redirect
from django.urls import path
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from crm.users.utils import user_has_perm
from crm.zetom.models import (
    DeletedValidationRequest, DepartmentsVariants, RequestNull,
)
from crm.zetom.services.visibility import visible_requests_for

from .base import DepartmentsDisplayMixin


@admin.register(DeletedValidationRequest)
class DeletedValidationRequestAdmin(DepartmentsDisplayMixin, ModelAdmin):
    change_form_template = "admin/zetom/deletedvalidationrequest/change_form.html"
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
        # Allow opening the change view so the Restore action works.
        return user_has_perm(request.user, "view_requests")

    def has_delete_permission(self, request, obj=None):
        return False

    # ---------- Queryset / submit bar / context ----------

    def get_queryset(self, request):
        return visible_requests_for(request.user, RequestNull.deleted_objects.all())

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
        view = self.admin_site.admin_view
        custom = [
            path(
                "<path:object_id>/restore/",
                view(self.restore_action),
                name="zetom_deletedvalidationrequest_restore",
            ),
            path(
                "<path:object_id>/hard-delete/",
                view(self.hard_delete_action),
                name="zetom_deletedvalidationrequest_hard_delete",
            ),
        ]
        return custom + urls

    # ---------- Restore / hard-delete actions ----------

    def _get_trashed_for_action(self, request, object_id, perm):
        """Perm + visibility gate against the deleted_objects manager.
        Returns (obj, None) or (None, redirect)."""
        if not user_has_perm(request.user, perm):
            messages.error(request, _("You don't have permission for this action."))
            return None, redirect("admin:zetom_deletedvalidationrequest_change", object_id)
        qs = visible_requests_for(request.user, RequestNull.deleted_objects.all())
        obj = qs.filter(pk=object_id).first()
        if obj is None:
            messages.error(request, _("Request not found."))
            return None, redirect("admin:zetom_deletedvalidationrequest_changelist")
        return obj, None

    @transaction.atomic
    def restore_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_deletedvalidationrequest_change", object_id)
        obj, denied = self._get_trashed_for_action(
            request, object_id, "change_request_status"
        )
        if denied is not None:
            return denied
        obj.undelete()
        # RequestNull has no status/StatusHistory — undelete is the whole
        # restore. Notify staff that a lead came back (best-effort).
        try:
            from crm.notification.services.request_restore import (
                notify_validation_request_restored,
            )
            notify_validation_request_restored(obj, actor=request.user)
        except Exception:  # noqa: BLE001 — notification must not block restore
            pass
        messages.success(request, _("Request restored to the Validation Window."))
        return redirect("admin:zetom_requestnull_validate", object_id)

    @transaction.atomic
    def hard_delete_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_deletedvalidationrequest_change", object_id)
        obj, denied = self._get_trashed_for_action(
            request, object_id, "delete_requests"
        )
        if denied is not None:
            return denied
        from safedelete.config import HARD_DELETE
        obj.delete(force_policy=HARD_DELETE)
        messages.success(request, _("Request permanently deleted."))
        return redirect("admin:zetom_deletedvalidationrequest_changelist")
