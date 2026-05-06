# Django imports
from django import forms
from django.contrib import admin, messages
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import path
# Crispy imports
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Field, Layout, Row
# Unfold imports
from unfold.admin import ModelAdmin
from unfold.decorators import action, display
from unfold.enums import ActionVariant

# Notification app imports
from crm.notification.services.notification_service import \
    send_notification_approve_null
from crm.status_manager.models import StatusHistory
from crm.status_manager.services.status_service import (handle_child_change,
                                                        save_child_with_status)
from crm.status_manager.services.statuses import RequestStatus
# Users app imports
from crm.users.utils import user_has_perm
# Zetom app imports
from crm.zetom.forms import (AddOferta, AddRequestFormMain, AddRequestFormNull,
                             AddWniosek, AddZlecenie)
from crm.zetom.models import (DepartmentsVariants, Oferta, RequestMain, RequestNull, Wniosek, DeletedRequest,
                              Zlecenie)
from crm.zetom.services.request_service import (approve_null_action,
                                                approve_oferta_action,
                                                approve_wniosek_action,
                                                approve_zlecenie_action)
from crm.zetom.services.status_orchestration import (ReasonRequired,
                                                     apply_status_change)
from crm.zetom.services.visibility import visible_requests_for



class ReasonForm(forms.Form):
    reason = forms.CharField(
        widget=forms.Textarea,
        label="Reason",
        required=True,
    )

    
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
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = visible_requests_for(request.user, qs)
        return qs.prefetch_related("assigned_to")

    @admin.display(description="Assigned")
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
        description="Status",
    )
    def colored_status(self, obj):
        display_names = {
            "new": "New",
            "in_progress": "In Progress",
            "waiting": "Waiting",
            "done": "Done",
        }
        return obj.status, display_names.get(obj.status, obj.status)


# AI-generated (unknown, legacy): LogEntryAdmin — read-only viewer for django admin log
@admin.register(LogEntry)
class LogEntryAdmin(ModelAdmin):  # Используем ModelAdmin от Unfold для красоты
    list_display = ("action_time", "user", "content_type", "object_repr", "action_flag")
    list_filter = ("action_flag", "content_type", "user")
    search_fields = ("object_repr", "change_message")

    # RBAC
    def has_view_permission(self, request, obj=None):
       return True

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RequestNull)
class RequestNullAdmin(BaseRequestAdmin):
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


class StatusHistoryInline(admin.TabularInline):
    model = StatusHistory
    extra = 0
    can_delete = False
    readonly_fields = ("old_status", "new_status", "reason", "changed_by", "changed_at")

    def has_add_permission(self, request, obj=None):
        return False



@admin.register(RequestMain)
class RequestMainAdmin(BaseRequestAdmin):
    form = AddRequestFormMain
    #inlines = [StatusHistoryInline] # показывает историю в админке 
    change_form_template = "admin/zetom/requestmain/change_form.html"
    list_display = ("created_at", "updated_at", "company_name", "department", "assignees_display", "colored_status" )
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
    warn_unsaved_form = True

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
        context["department_choices"] = DepartmentsVariants.choices
        has_obj = obj is not None and obj.pk is not None
        context["ofertas"] = obj.oferta_set.order_by("-created_at") if has_obj else []
        context["zlecenia"] = obj.zlecenie_set.order_by("-created_at") if has_obj else []
        context["wnioski"] = obj.wniosek_set.order_by("-created_at") if has_obj else []
        if has_obj:
            assigned_ids = obj.assigned_to.values_list("id", flat=True)
            context["available_users"] = (
                User.objects.filter(is_active=True)
                .exclude(id__in=assigned_ids)
                .order_by("username")
            )
        else:
            context["available_users"] = User.objects.none()
        context["client_files"] = []

        return super().render_change_form(request, context, *args, **kwargs)


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
        ]
        return custom + urls

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
        messages.success(
            request,
            f"Assigned {user.get_full_name() or user.username}.",
        )
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
        messages.success(
            request,
            f"Removed {user.get_full_name() or user.username}.",
        )
        return redirect("admin:zetom_requestmain_change", object_id)

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


    def oferta_action(self, request, object_id):
        oferta = approve_oferta_action(object_id)
        messages.info(request, f"Redirecting to Oferta: {object_id}")
        return redirect("admin:zetom_oferta_change", oferta.pk)

    def zlecenie_action(self, request, object_id):
        zlecenie = approve_zlecenie_action(object_id)
        messages.info(request, f"Redirecting to Zlecenie: {object_id}")
        return redirect("admin:zetom_zlecenie_change", zlecenie.pk)

    def wniosek_action(self, request, object_id):
        wniosek = approve_wniosek_action(object_id)
        messages.info(request, f"Redirecting to Wniosek: {object_id}")
        return redirect("admin:zetom_wniosek_change", wniosek.pk)


# AI-suggested (claude-opus-4-7, 2026-04-23): save_model во всех трёх админках ниже делегирует в save_child_with_status — паттерн предложен Claude, код написал пользователь.
@admin.register(Oferta)
class OfertaAdmin(BaseRequestAdmin):
    actions = []
    form = AddOferta
    list_display = ("from_main", "created_at", "updated_at", "company_name", "department", "assignees_display", "colored_status")
    readonly_fields = ("from_main",)
    fields = (
        "from_main",
        "phone",
        "status",
        "department",
        "assigned_to",
        "email",
        "company_name",
        "company_nip",
        "price",
        "notes",
    )
    warn_unsaved_form = True

    def save_model(self, request, obj, form, change):
        if save_child_with_status(request, obj, form, change, messages):
            super().save_model(request, obj, form, change)

@admin.register(Zlecenie)
class ZlecenieAdmin(BaseRequestAdmin):
    actions = []
    form = AddZlecenie
    list_display = ("from_main", "created_at", "updated_at", "company_name", "department", "assignees_display", "colored_status")
    readonly_fields = ("from_main",)
    fields = (
        "from_main",
        "deadline",
        "phone",
        "status",
        "department",
        "assigned_to",
        "email",
        "company_name",
        "company_nip",
        "price",
        "notes",
    )
    warn_unsaved_form = True

    def save_model(self, request, obj, form, change):
        if save_child_with_status(request, obj, form, change, messages):
            super().save_model(request, obj, form, change)


@admin.register(Wniosek)
class WniosekAdmin(BaseRequestAdmin):
    actions = []
    form = AddWniosek
    list_display = ("from_main", "created_at", "updated_at", "company_name", "department", "assignees_display", "colored_status")
    readonly_fields = ("from_main",)
    fields = (
        "from_main",
        "application_number",
        "phone",
        "status",
        "department",
        "assigned_to",
        "email",
        "company_name",
        "company_nip",
        "notes",
    )
    warn_unsaved_form = True

    def save_model(self, request, obj, form, change):
        if save_child_with_status(request, obj, form, change, messages):
            super().save_model(request, obj, form, change)

@admin.register(DeletedRequest)
class DeletedRequestAdmin(ModelAdmin):
    list_display = ("created_at", "company_name", "department")
    actions_detail = ["restore_action"]
    readonly_fields = (
        "status", "full_name", "phone", "department", "assigned_to",
        "company_name", "company_nip", "email", "address", "message",
    )
    fields = (
        "status", "full_name", "phone", "department", "assigned_to",
        "company_name", "company_nip", "email", "address", "message",
    )

    def get_queryset(self, request):
        return RequestMain.deleted_objects.all()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_requests")  # ← разрешить для action

    def has_delete_permission(self, request, obj=None):
        return False

    @action(description="Restore", icon="restore", url_path="restore")
    def restore_action(self, request, object_id):
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
        return redirect("admin:zetom_requestmain_changelist")

        
