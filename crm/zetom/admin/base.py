"""Shared admin building blocks: forms, mixins, base ModelAdmin.

Imported by every admin submodule. Keep small and dependency-light —
this module is loaded first and shouldn't pull in Crispy / heavy stuff.
"""
from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import display

from crm.users.utils import user_has_perm
from crm.zetom.models import DepartmentsVariants, StepNote
from crm.zetom.services.visibility import visible_requests_for


class ReasonForm(forms.Form):
    """Single-field reason form used by status-change reason flow
    (cancel / delete / inactive) and by Trash Restore."""
    reason = forms.CharField(
        widget=forms.Textarea,
        label=_("Reason"),
        required=True,
    )


class StepNoteCreateForm(forms.Form):
    action = forms.CharField(max_length=255, required=False)
    text = forms.CharField(required=True)
    next_contact_at = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M"],
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

    class Media:
        css = {
            "all": ("zetom/css/step_notes.css",),
        }

    def get_urls(self):
        urls = super().get_urls()
        opts = self.model._meta
        custom = [
            path(
                "<path:object_id>/step-notes/create/",
                self.admin_site.admin_view(self.step_note_create_action),
                name=f"{opts.app_label}_{opts.model_name}_step_note_create",
            ),
        ]
        return custom + urls

    def _get_obj_for_step_note(self, request, object_id):
        obj = self.get_queryset(request).filter(pk=object_id).first()
        if obj is None:
            return None, HttpResponseForbidden(_("Request not found."))
        if not self.has_change_permission(request, obj):
            return None, HttpResponseForbidden(_("You don't have permission for this action."))
        return obj, None

    def step_note_create_action(self, request, object_id):
        if request.method != "POST":
            return redirect(self._change_url_for_id(object_id))

        obj, forbidden = self._get_obj_for_step_note(request, object_id)
        if forbidden is not None:
            return forbidden

        form = StepNoteCreateForm(request.POST)
        if not form.is_valid():
            messages.error(request, _("Could not add note. Check note text/date format."))
            return redirect(self._change_url_for_id(object_id))

        StepNote.objects.create(
            author=request.user,
            action=form.cleaned_data["action"],
            text=form.cleaned_data["text"],
            next_contact_at=form.cleaned_data["next_contact_at"],
            target=obj,
        )
        messages.success(request, _("Step note added."))
        return redirect(self._change_url_for_id(object_id))

    def _change_url_for_id(self, object_id):
        opts = self.model._meta
        return reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[object_id])

    def _build_step_notes_context(self, obj):
        opts = self.model._meta
        if not obj or not obj.pk:
            return {
                "step_notes_enabled": False,
                "step_notes": [],
                "step_notes_create_url": "",
                "step_notes_target_label": "",
            }
        return {
            "step_notes_enabled": True,
            "step_notes": obj.step_notes.select_related("author").all()[:50],
            "step_notes_create_url": reverse(
                f"admin:{opts.app_label}_{opts.model_name}_step_note_create",
                args=[obj.pk],
            ),
            "step_notes_target_label": str(obj),
        }

    def render_change_form(self, request, context, *args, **kwargs):
        obj = context.get("original")
        context.update(self._build_step_notes_context(obj))
        return super().render_change_form(request, context, *args, **kwargs)

    # claude — "Create new" from the Client Detail tabs lands here with
    # ?client=<pk>. The clients M2M uses a through-model so it can't be a form
    # field; instead we pre-fill the request's own contact snapshot from the
    # client, which is what the validator would copy anyway.
    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        client_id = request.GET.get("client")
        if client_id:
            from crm.clients.models import Client
            client = Client.objects.filter(pk=client_id).first()
            if client:
                # claude — фирменные поля снапшота берём из связанной Company
                # (company_* уезжают с Client в 2c).
                link = client.company_links.first()
                company = link.company if link else None
                initial.update({
                    "first_name": client.first_name,
                    "last_name": client.last_name,
                    "company_name": company.name if company else "",
                    "company_nip": company.nip if company else "",
                    "phone": client.phone,
                    "email": client.email,
                })
        return initial

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
