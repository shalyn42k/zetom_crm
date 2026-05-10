"""Main RequestMain admin — custom change-view with status flow,
reason form routing, departments / assignee management, document
creation actions, and a flatter submit bar.

Largest admin in the project; lives in its own module so the rest of
the package stays scannable.
"""
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Field, Layout, Row
from django.contrib import admin, messages
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import path

from crm.status_manager.models import StatusHistory
from crm.status_manager.services.statuses import RequestStatus
from crm.zetom.forms import AddRequestFormMain
from crm.zetom.models import DepartmentsVariants, RequestMain, RequestSource
from crm.zetom.services.request_service import (approve_oferta_action,
                                                approve_wniosek_action,
                                                approve_zlecenie_action)
from crm.zetom.services.status_orchestration import (ReasonRequired,
                                                     apply_status_change)

from .base import BaseRequestAdmin, ReasonForm
from crm.status_manager.services.statuses import RequestStatus

@admin.register(RequestMain)
class RequestMainAdmin(BaseRequestAdmin):
    
    form = AddRequestFormMain
    change_form_template = "admin/zetom/requestmain/change_form.html"
    list_display = (
        "created_at", "updated_at", "company_name",
        "display_departments", "assignees_display", "colored_status", "source",
    )
    list_filter = ("source",)
    fields = (
        "first_name",
        "last_name",
        "phone",
        "departments",
        "company_name",
        "company_nip",
        "email",
        "address",
        "message",
        "source",
    )
    warn_unsaved_form = True

    class Media:
        js = [
            "client/client_autofill.js",
            "client/client_search.js",
        ]

    def get_queryset(self, request):
       qs = super().get_queryset(request)
       return qs.exclude(status__in=[RequestStatus.cancelled, RequestStatus.deleted])


    def get_changeform_initial_data(self, request):
        return {"source": RequestSource.PHONE}


    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["show_save_and_add_another"] = False
        extra_context["show_save_and_continue"] = False
        return super().changeform_view(request, object_id, form_url, extra_context)

    def response_change(self, request, obj):
        if (
            "_continue" not in request.POST
            and "_addanother" not in request.POST
            and "_saveasnew" not in request.POST
        ):
            return redirect("admin:zetom_requestmain_change", obj.pk)
        return super().response_change(request, obj)

    def response_add(self, request, obj, post_url_continue=None):
        if "_continue" not in request.POST and "_addanother" not in request.POST:
            return redirect("admin:zetom_requestmain_change", obj.pk)
        return super().response_add(request, obj, post_url_continue)

    # ---------- Delete (status flip + safedelete) ----------

    def _flip_to_deleted(self, request, obj):
        if obj.status != RequestStatus.deleted:
            old_status = obj.status
            obj.status = RequestStatus.deleted
            obj.save(update_fields=["status"])
            StatusHistory.objects.create(
                request=obj,
                old_status=old_status,
                new_status=RequestStatus.deleted,
                reason="Deleted via admin",
                changed_by=request.user,
            )

    @transaction.atomic
    def delete_model(self, request, obj):
        self._flip_to_deleted(request, obj)
        super().delete_model(request, obj)

    @transaction.atomic
    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self._flip_to_deleted(request, obj)
        super().delete_queryset(request, queryset)

    # ---------- Custom layout context ----------

    def render_change_form(self, request, context, *args, **kwargs):
        obj = context.get("original")

        adminform = context.get("adminform")
        if adminform is not None:
            form = adminform.form
            helper = FormHelper()
            helper.form_tag = False
            helper.disable_csrf = True
            helper.layout = Layout(
                Row(
                    Column("email", css_class="rm-col-6"),
                    Column("phone", css_class="rm-col-6"),
                    css_class="rm-row",
                ),
                Field("address"),
                Field("message"),
            )
            form.helper = helper
            context["form"] = form

        context["status_choices"] = RequestStatus.choices
        has_obj = obj is not None and obj.pk is not None
        context["ofertas"] = obj.oferta_set.order_by("-created_at") if has_obj else []
        context["zlecenia"] = obj.zlecenie_set.order_by("-created_at") if has_obj else []
        context["wnioski"] = obj.wniosek_set.order_by("-created_at") if has_obj else []
        context["history_entries"] = (
            obj.status_history.select_related("changed_by").order_by("-changed_at")
            if has_obj else []
        )
        if has_obj:
            assigned_ids = obj.assigned_to.values_list("id", flat=True)
            context["available_users"] = (
                User.objects.filter(is_active=True)
                .exclude(id__in=assigned_ids)
                .order_by("username")
            )
            assigned_codes = list(obj.departments or [])
            dept_labels = dict(DepartmentsVariants.choices)
            context["assigned_departments"] = [
                (code, dept_labels.get(code, code)) for code in assigned_codes
            ]
            context["available_departments"] = [
                (code, label) for code, label in DepartmentsVariants.choices
                if code not in assigned_codes
            ]
        else:
            context["available_users"] = User.objects.none()
            context["assigned_departments"] = []
            context["available_departments"] = []
        profile = getattr(request.user, "profile", None)
        context["user_department"] = profile.department if profile else None
        context["source_display"] = obj.get_source_display() if has_obj else ""

        return super().render_change_form(request, context, *args, **kwargs)

    # ---------- Custom URL endpoints ----------

    def get_urls(self):
        urls = super().get_urls()
        view = self.admin_site.admin_view
        custom = [
            path(
                "<path:object_id>/apply-status/",
                view(self.apply_status_action),
                name="zetom_requestmain_apply_status",
            ),
            path(
                "<path:object_id>/oferta/",
                view(self.oferta_action),
                name="zetom_requestmain_oferta_action",
            ),
            path(
                "<path:object_id>/zlecenie/",
                view(self.zlecenie_action),
                name="zetom_requestmain_zlecenie_action",
            ),
            path(
                "<path:object_id>/wniosek/",
                view(self.wniosek_action),
                name="zetom_requestmain_wniosek_action",
            ),
            path(
                "<path:object_id>/assign-user/",
                view(self.assign_user_action),
                name="zetom_requestmain_assign_user",
            ),
            path(
                "<path:object_id>/unassign-user/<int:user_id>/",
                view(self.unassign_user_action),
                name="zetom_requestmain_unassign_user",
            ),
            path(
                "<path:object_id>/add-department/",
                view(self.add_department_action),
                name="zetom_requestmain_add_department",
            ),
            path(
                "<path:object_id>/remove-department/<str:dept_code>/",
                view(self.remove_department_action),
                name="zetom_requestmain_remove_department",
            ),
        ]
        return custom + urls

    # ---------- Department actions ----------

    def add_department_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)

        obj = RequestMain.objects.get(pk=object_id)
        code = request.POST.get("dept_code")
        if code not in DepartmentsVariants.values:
            messages.error(request, "Invalid department.")
            return redirect("admin:zetom_requestmain_change", object_id)
        if code in (obj.departments or []):
            messages.info(request, "Already assigned.")
            return redirect("admin:zetom_requestmain_change", object_id)

        obj.departments = list(obj.departments or []) + [code]
        obj.save(update_fields=["departments"])
        label = dict(DepartmentsVariants.choices).get(code, code)
        messages.success(request, f"Added {label}.")
        return redirect("admin:zetom_requestmain_change", object_id)

    def remove_department_action(self, request, object_id, dept_code):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)

        obj = RequestMain.objects.get(pk=object_id)
        if dept_code in (obj.departments or []):
            obj.departments = [c for c in obj.departments if c != dept_code]
            obj.save(update_fields=["departments"])
            label = dict(DepartmentsVariants.choices).get(dept_code, dept_code)
            messages.success(request, f"Removed {label}.")
        return redirect("admin:zetom_requestmain_change", object_id)

    # ---------- User actions ----------

    def assign_user_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)

        obj = RequestMain.objects.get(pk=object_id)
        user_id = request.POST.get("user_id")
        if not user_id:
            messages.error(request, "No user selected.")
            return redirect("admin:zetom_requestmain_change", object_id)
        try:
            user = User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            messages.error(request, "User not found.")
            return redirect("admin:zetom_requestmain_change", object_id)

        obj.assigned_to.add(user)
        messages.success(request, f"Assigned {user.get_full_name() or user.username}.")
        return redirect("admin:zetom_requestmain_change", object_id)

    def unassign_user_action(self, request, object_id, user_id):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)

        obj = RequestMain.objects.get(pk=object_id)
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            messages.error(request, "User not found.")
            return redirect("admin:zetom_requestmain_change", object_id)

        obj.assigned_to.remove(user)
        messages.success(request, f"Removed {user.get_full_name() or user.username}.")
        return redirect("admin:zetom_requestmain_change", object_id)

    # ---------- Status flow ----------

    def apply_status_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)

        obj = RequestMain.objects.get(pk=object_id)
        new_status = request.POST.get("new_status")
        reason = request.POST.get("reason") or None

        try:
            apply_status_change(obj, request.user, new_status, reason=reason)
        except ReasonRequired:
            form = ReasonForm()
            return render(request, "admin/zetom/requestmain/reason_form.html", {
                "form": form,
                "obj": obj,
                "new_status": new_status,
                **self.admin_site.each_context(request),
            })
        except ValueError as e:
            messages.error(request, str(e))
            return redirect("admin:zetom_requestmain_change", object_id)

        messages.success(request, f"Status changed to {new_status}.")
        if new_status == RequestStatus.deleted:
            return redirect("admin:zetom_requestmain_changelist")
        return redirect("admin:zetom_requestmain_change", object_id)

    # ---------- Document creation actions ----------

    def oferta_action(self, request, object_id):
        approve_oferta_action(object_id)
        messages.success(request, "Offer created.")
        return redirect("admin:zetom_requestmain_change", object_id)

    def zlecenie_action(self, request, object_id):
        approve_zlecenie_action(object_id)
        messages.success(request, "Order created.")
        return redirect("admin:zetom_requestmain_change", object_id)

    def wniosek_action(self, request, object_id):
        approve_wniosek_action(object_id)
        messages.success(request, "Application created.")
        return redirect("admin:zetom_requestmain_change", object_id)
