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
from django.utils.translation import gettext_lazy as _

from crm.status_manager.models import StatusHistory
from crm.status_manager.services.statuses import RequestStatus
from crm.users.utils import user_has_perm
from crm.zetom.forms import AddRequestFormMain
from crm.zetom.models import DepartmentsVariants, RequestMain, RequestSource
from crm.zetom.services.per_req_perms import (
    can_assign_anyone, can_assign_target, can_manage_owners,
    can_resolve_review, can_unassign_target, is_owner_of_req,
)
from crm.zetom.services.request_service import (
    approve_oferta_action, approve_wniosek_action, approve_zlecenie_action,
)
from crm.zetom.services.status_orchestration import (
    ReasonRequired, apply_status_change,
)
from crm.zetom.services.visibility import visible_requests_for

from .base import BaseRequestAdmin, ReasonForm
from .requestmain_mail import RequestMailMixin
from .requestmain_resolve_review import (
    RequestResolveReviewMixin, latest_open_review,
)
from .requestmain_review import RequestReviewMixin


@admin.register(RequestMain)
class RequestMainAdmin(
    RequestMailMixin,
    RequestReviewMixin,
    RequestResolveReviewMixin,
    BaseRequestAdmin,
):
    
    form = AddRequestFormMain
    change_form_template = "admin/zetom/requestmain/change_form.html"
    list_display = (
        "created_at", "updated_at", "company_name",
        "display_departments", "assignees_display", "colored_status", "source",
    )
    search_fields = (
      "first_name",
      "last_name",
      "company_name",
      "company_nip",
      "email",
    )
    list_filter = ("source", "status")
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

    def get_fields(self, request, obj=None):
        # source выбирается только при создании; на странице редактирования
        # для него нет виджета в шаблоне, поэтому убираем поле из формы,
        # иначе оно валится с "This field is required" при каждом Save.
        fields = list(super().get_fields(request, obj))
        if obj is not None and "source" in fields:
            fields.remove("source")
        return fields


    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["show_save_and_add_another"] = False
        extra_context["show_save_and_continue"] = False
        return super().changeform_view(request, object_id, form_url, extra_context)

    def response_change(self, request, obj):
        return redirect("admin:zetom_requestmain_change", obj.pk)

    def response_add(self, request, obj, post_url_continue=None):
        return redirect("admin:zetom_requestmain_change", obj.pk)

    # ---------- Delete (status flip + safedelete) ----------

    def _flip_to_deleted(self, request, obj):
        if obj.status != RequestStatus.deleted:
            old_status = obj.status
            obj.status = RequestStatus.deleted
            obj.save(update_fields=["status"])
            # claude — single-object delete (`delete_view`) stashes the reason
            # on the instance; bulk `delete_queryset` doesn't have a reason
            # form, so it falls back to a generic label.
            reason = getattr(obj, "_delete_reason", None) or "Deleted via admin"
            StatusHistory.objects.create(
                request=obj,
                old_status=old_status,
                new_status=RequestStatus.deleted,
                reason=reason,
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

    # claude — bottom "Delete" button on the change form now goes through
    # the same reason-form flow as the right-side Status → Delete action,
    # instead of silently using "Deleted via admin" as the reason.
    def delete_view(self, request, object_id, extra_context=None):
        obj = self.get_object(request, object_id)
        if obj is None or not self.has_delete_permission(request, obj):
            return super().delete_view(request, object_id, extra_context)

        if request.method == "POST":
            reason = (request.POST.get("reason") or "").strip()
            if reason:
                obj._delete_reason = reason
                self.delete_model(request, obj)
                messages.success(request, "Request deleted.")
                return redirect("admin:zetom_requestmain_changelist")
            messages.error(request, "Reason is required.")

        form = ReasonForm()
        return render(
            request,
            "admin/zetom/requestmain/reason_form.html",
            {
                "form": form,
                "obj": obj,
                **self.admin_site.each_context(request),
            },
        )

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
        # claude — было user_department (одиночка). Стало списком, шаблон
        # подсвечивает «свои» чипы через `{% if code in user_departments %}`.
        context["user_departments"] = profile.departments if profile else []
        context["source_display"] = obj.get_source_display() if has_obj else ""

        # claude — picker для "Request review". default = каскад owners →
        # dep_heads → admins, фильтрованный правилом «sender может слать
        # target'у». extras = все active dep_heads + admins, которых нет в
        # default. owners-из-default рендерятся read-only в шаблоне.
        if has_obj:
            from crm.notification.services.recipients import (
                review_candidates_for,
            )
            review_default, review_extras = review_candidates_for(obj, request.user)
            owner_ids_in_default = {u.pk for u in review_default if u.pk in obj.owners.values_list("id", flat=True)}
            context["review_default_locked"] = [u for u in review_default if u.pk in owner_ids_in_default]
            context["review_default_optional"] = [u for u in review_default if u.pk not in owner_ids_in_default]
            context["review_extras"] = review_extras
        else:
            context["review_default_locked"] = []
            context["review_default_optional"] = []
            context["review_extras"] = []

        # claude — гейтинг "Resolve review" в actions_card:
        #   can_resolve_review — per-Req пермишена (роль resolve_review ИЛИ owner);
        #   open_review        — Notification(REVIEW_REQUEST) если открыт, иначе None.
        # Сам Notification пробрасываем в шаблон, чтобы модалка показала
        # автора, дату и комментарий специалиста до принятия решения.
        context["can_resolve_review"] = (
            has_obj and can_resolve_review(request.user, obj)
        )
        context["open_review"] = latest_open_review(obj) if has_obj else None
        context["has_open_review"] = context["open_review"] is not None

        # claude — контекст для assigned_users.html: per-Req флаги owner +
        # права на управление списком. Список assigned сортируем owners-first,
        # потом по username, чтобы UI был стабильным.
        if has_obj:
            owner_ids = set(obj.owners.values_list("id", flat=True))
            assigned = list(
                obj.assigned_to.select_related("profile__role").order_by("username")
            )
            assigned.sort(key=lambda u: (u.id not in owner_ids, u.username))
            context["assigned_users_ordered"] = assigned
            context["owner_ids"] = owner_ids
            context["can_manage_owners"] = can_manage_owners(request.user, obj)
            context["can_assign_anyone"] = can_assign_anyone(request.user, obj)
            context["is_owner_self"] = is_owner_of_req(request.user, obj)
            # Per-юзер права на × unassign (нужно в шаблоне на каждую строку).
            context["assign_target_rights"] = {
                u.pk: {
                    "can_unassign": can_unassign_target(request.user, u, obj),
                }
                for u in assigned
            }
            # Доступные для add: и фильтруем по can_assign_target на каждом.
            context["assignable_users"] = [
                u for u in context["available_users"]
                if can_assign_target(request.user, u, obj)
            ]
        else:
            context["assigned_users_ordered"] = []
            context["owner_ids"] = set()
            context["can_manage_owners"] = False
            context["can_assign_anyone"] = False
            context["is_owner_self"] = False
            context["assign_target_rights"] = {}
            context["assignable_users"] = []

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
                "<path:object_id>/set-owner/<int:user_id>/",
                view(self.set_owner_action),
                name="zetom_requestmain_set_owner",
            ),
            path(
                "<path:object_id>/unset-owner/<int:user_id>/",
                view(self.unset_owner_action),
                name="zetom_requestmain_unset_owner",
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

    # ---------- POST-action gate ----------

    # claude
    def _get_req_for_action(self, request, object_id, perm):
        """Resolve RequestMain for a custom POST endpoint guarded by a
        role-permission code (например, edit_requests / assign_requests).

        Returns (obj, None) on success, or (None, HttpResponse) when the
        caller should bail out — either missing permission, hidden by
        visibility filter, or pk not found. The redirect target differs
        on purpose: perm-denied lands back on the same Req (so the user
        sees the error message in context), whereas a missing/hidden pk
        lands on the changelist (the Req either doesn't exist or the
        user has no business seeing it).
        """
        if not user_has_perm(request.user, perm):
            messages.error(request, _("You don't have permission for this action."))
            return None, redirect("admin:zetom_requestmain_change", object_id)
        qs = visible_requests_for(request.user, RequestMain.objects.all())
        obj = qs.filter(pk=object_id).first()
        if obj is None:
            messages.error(request, _("Request not found."))
            return None, redirect("admin:zetom_requestmain_changelist")
        return obj, None

    # claude
    def _get_req_visible(self, request, object_id):
        """Same as `_get_req_for_action`, но без role-perm-чека.

        Используется там, где гейт контекстный (per-Req): assign/unassign,
        set/unset owner. Право решает уже сам action через
        `services.per_req_perms.*`.
        """
        qs = visible_requests_for(request.user, RequestMain.objects.all())
        obj = qs.filter(pk=object_id).first()
        if obj is None:
            messages.error(request, _("Request not found."))
            return None, redirect("admin:zetom_requestmain_changelist")
        return obj, None

    # ---------- Department actions ----------

    def add_department_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)
        obj, denied = self._get_req_for_action(request, object_id, "edit_requests")
        if denied is not None:
            return denied

        code = request.POST.get("dept_code")
        if code not in DepartmentsVariants.values:
            messages.error(request, _("Invalid department."))
            return redirect("admin:zetom_requestmain_change", object_id)
        if code in (obj.departments or []):
            messages.info(request, _("Already assigned."))
            return redirect("admin:zetom_requestmain_change", object_id)

        obj.departments = list(obj.departments or []) + [code]
        obj.save(update_fields=["departments"])
        label = dict(DepartmentsVariants.choices).get(code, code)
        messages.success(request, _("Added %(label)s.") % {"label": label})
        return redirect("admin:zetom_requestmain_change", object_id)

    def remove_department_action(self, request, object_id, dept_code):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)
        obj, denied = self._get_req_for_action(request, object_id, "edit_requests")
        if denied is not None:
            return denied

        if dept_code in (obj.departments or []):
            obj.departments = [c for c in obj.departments if c != dept_code]
            obj.save(update_fields=["departments"])
            label = dict(DepartmentsVariants.choices).get(dept_code, dept_code)
            messages.success(request, _("Removed %(label)s.") % {"label": label})
        return redirect("admin:zetom_requestmain_change", object_id)

    # ---------- User actions ----------

    # claude — per-Req пермишена: admin/dep_head-of-Req могут любого,
    # owner может только specialist'ов. Подробно см.
    # memory/project_per_req_permissions.md.
    def assign_user_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)
        obj, denied = self._get_req_visible(request, object_id)
        if denied is not None:
            return denied

        user_id = request.POST.get("user_id")
        if not user_id:
            messages.error(request, _("No user selected."))
            return redirect("admin:zetom_requestmain_change", object_id)
        try:
            user = User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            messages.error(request, _("User not found."))
            return redirect("admin:zetom_requestmain_change", object_id)

        if not can_assign_target(request.user, user, obj):
            messages.error(request, _("You can't assign this user."))
            return redirect("admin:zetom_requestmain_change", object_id)

        obj.assigned_to.add(user)
        messages.success(
            request,
            _("Assigned %(name)s.") % {"name": user.get_full_name() or user.username},
        )
        return redirect("admin:zetom_requestmain_change", object_id)

    def unassign_user_action(self, request, object_id, user_id):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)
        obj, denied = self._get_req_visible(request, object_id)
        if denied is not None:
            return denied

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            messages.error(request, _("User not found."))
            return redirect("admin:zetom_requestmain_change", object_id)

        if not can_unassign_target(request.user, user, obj):
            messages.error(request, _("You can't unassign this user."))
            return redirect("admin:zetom_requestmain_change", object_id)

        # claude — unassign снимает и owner-флаг (owners ⊆ assigned).
        obj.assigned_to.remove(user)
        obj.owners.remove(user)
        messages.success(
            request,
            _("Removed %(name)s.") % {"name": user.get_full_name() or user.username},
        )
        return redirect("admin:zetom_requestmain_change", object_id)

    # claude — per-Req пермишена на owners: только admin / dep_head-of-Req.
    def set_owner_action(self, request, object_id, user_id):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)
        obj, denied = self._get_req_visible(request, object_id)
        if denied is not None:
            return denied
        if not can_manage_owners(request.user, obj):
            messages.error(request, _("You don't have permission for this action."))
            return redirect("admin:zetom_requestmain_change", object_id)
        try:
            user = User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            messages.error(request, _("User not found."))
            return redirect("admin:zetom_requestmain_change", object_id)
        # Owner ⊆ assigned — нельзя сделать овнером того, кого нет в assigned.
        if not obj.assigned_to.filter(pk=user.pk).exists():
            messages.error(request, _("User must be assigned before becoming owner."))
            return redirect("admin:zetom_requestmain_change", object_id)
        obj.owners.add(user)
        messages.success(
            request,
            _("%(name)s is now an owner.") % {"name": user.get_full_name() or user.username},
        )
        return redirect("admin:zetom_requestmain_change", object_id)

    def unset_owner_action(self, request, object_id, user_id):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)
        obj, denied = self._get_req_visible(request, object_id)
        if denied is not None:
            return denied
        if not can_manage_owners(request.user, obj):
            messages.error(request, _("You don't have permission for this action."))
            return redirect("admin:zetom_requestmain_change", object_id)
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            messages.error(request, _("User not found."))
            return redirect("admin:zetom_requestmain_change", object_id)
        obj.owners.remove(user)
        messages.success(
            request,
            _("%(name)s is no longer an owner.") % {"name": user.get_full_name() or user.username},
        )
        return redirect("admin:zetom_requestmain_change", object_id)

    # ---------- Status flow ----------

    def apply_status_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)
        obj, denied = self._get_req_for_action(
            request, object_id, "change_request_status"
        )
        if denied is not None:
            return denied

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

        messages.success(
            request,
            _("Status changed to %(status)s.") % {"status": new_status},
        )
        if new_status == RequestStatus.deleted:
            return redirect("admin:zetom_requestmain_changelist")
        return redirect("admin:zetom_requestmain_change", object_id)

    # ---------- Document creation actions ----------

    def oferta_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)
        _obj, denied = self._get_req_for_action(request, object_id, "edit_requests")
        if denied is not None:
            return denied
        approve_oferta_action(object_id)
        messages.success(request, _("Offer created."))
        return redirect("admin:zetom_requestmain_change", object_id)

    def zlecenie_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)
        _obj, denied = self._get_req_for_action(request, object_id, "edit_requests")
        if denied is not None:
            return denied
        approve_zlecenie_action(object_id)
        messages.success(request, _("Order created."))
        return redirect("admin:zetom_requestmain_change", object_id)

    def wniosek_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)
        _obj, denied = self._get_req_for_action(request, object_id, "edit_requests")
        if denied is not None:
            return denied
        approve_wniosek_action(object_id)
        messages.success(request, _("Application created."))
        return redirect("admin:zetom_requestmain_change", object_id)
