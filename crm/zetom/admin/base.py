"""Shared admin building blocks: forms, mixins, base ModelAdmin.

Imported by every admin submodule. Keep small and dependency-light —
this module is loaded first and shouldn't pull in Crispy / heavy stuff.
"""
from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import display

from crm.users.utils import user_has_perm
from crm.zetom.models import DepartmentsVariants
from crm.zetom.services.visibility import visible_requests_for


class ReasonForm(forms.Form):
    """Single-field reason form used by status-change reason flow
    (cancel / delete / inactive) and by Trash Restore."""
    reason = forms.CharField(
        widget=forms.Textarea,
        label=_("Reason"),
        required=True,
    )


class DepartmentsDisplayMixin:
    """Renders the ArrayField departments as a comma-separated list of
    labels in admin list_display / readonly_fields."""

    @admin.display(description=_("Departments"))
    def display_departments(self, obj):
        labels = dict(DepartmentsVariants.choices)
        return ", ".join(str(labels.get(code, code)) for code in obj.departments) or "—"


class BaseRequestAdmin(DepartmentsDisplayMixin, ModelAdmin):
    """Shared base for RequestNull / RequestMain / Oferta / Zlecenie /
    Wniosek admins. Wires RBAC permissions and visibility filter."""

    # RBAC
    def has_view_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_requests")

    def has_add_permission(self, request):
        return user_has_perm(request.user, "edit_requests")

    def has_change_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_requests")

    def has_delete_permission(self, request, obj=None):
        return user_has_perm(request.user, "delete_requests")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = visible_requests_for(request.user, qs)
        return qs.prefetch_related("assigned_to")

    @admin.display(description=_("Assigned"))
    def assignees_display(self, obj):
        users = obj.assigned_to.all()
        return ", ".join(u.username for u in users) or "—"

    @display(
        label={
            "new": "info",
            "in_progress": "warning",
            "waiting": "secondary",
            "done": "success",
        },
        description=_("Status"),
    )
    def colored_status(self, obj):
        from crm.status_manager.services.statuses import Status
        return obj.status, str(Status(obj.status).label) if obj.status in Status.values else obj.status
