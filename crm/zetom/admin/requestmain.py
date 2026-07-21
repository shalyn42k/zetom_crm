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
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from crm.clients.models import Client
from crm.notification.services.inapp_service import (
    dismiss_pending_review_requests,
)
from crm.status_manager.models import StatusHistory
from crm.status_manager.services.statuses import RequestStatus
from crm.users.utils import user_has_perm
from crm.zetom.forms import AddRequestFormMain
from crm.zetom.models import (
    DepartmentsVariants, RequestAttachment, RequestClientLink, RequestMain,
    RequestSource,
)
from crm.zetom.services.duplicate_matcher import find_candidates
from crm.zetom.services.per_req_perms import (
    can_assign_anyone, can_assign_target, can_manage_owners,
    can_resolve_review, can_unassign_target, is_owner_of_req,
)
from crm.zetom.services.request_duplicate_finder import find_request_duplicates
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
        css = {
            "all": ("zetom/css/step_notes.css",),
        }
        js = [
            "client/client_autofill.js",
            "client/client_search.js",
            "zetom/js/requestmain_dupe_check.js",
            "zetom/js/requestmain_client_link.js",
        ]

    def get_queryset(self, request):
       qs = super().get_queryset(request)
       return qs.exclude(status__in=[RequestStatus.cancelled, RequestStatus.deleted])


    def get_changeform_initial_data(self, request):
        # claude — keep the default source, plus client prefill from BaseRequestAdmin.
        initial = super().get_changeform_initial_data(request)
        initial.setdefault("source", RequestSource.PHONE)
        return initial

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

    @transaction.atomic
    def response_add(self, request, obj, post_url_continue=None):
        # claude — popup mini-VW choices: link several existing clients and/or
        # create a new one, then assign. Empty selection = leave unlinked.
        for raw_pk in request.POST.getlist("popup_client_ids"):
            try:
                client_pk = int(raw_pk)
            except (TypeError, ValueError):
                continue
            cl = Client.objects.filter(pk=client_pk).first()
            if cl:
                RequestClientLink.objects.get_or_create(
                    request=obj, client=cl, defaults={"linked_by": request.user}
                )
        if request.POST.get("popup_create_new"):
            cl = Client.objects.create(
                first_name=request.POST.get("first_name") or obj.first_name,
                last_name=request.POST.get("last_name") or obj.last_name,
                company_name=request.POST.get("company_name") or obj.company_name,
                company_nip=request.POST.get("company_nip") or obj.company_nip or None,
                phone=request.POST.get("phone") or obj.phone,
                email=request.POST.get("email") or obj.email,
            )
            RequestClientLink.objects.get_or_create(
                request=obj, client=cl, defaults={"linked_by": request.user}
            )
        departments = request.POST.getlist("popup_departments")
        owners_raw = request.POST.getlist("popup_owners")
        if departments:
            obj.departments = list(departments)
            obj.save(update_fields=["departments"])
        if owners_raw:
            owner_users = list(User.objects.filter(pk__in=owners_raw, is_active=True))
            obj.assigned_to.set(owner_users)
            obj.owners.set(owner_users)
        for f in request.FILES.getlist("attachments"):
            RequestAttachment.objects.create(request_main=obj, file=f, uploaded_by=request.user)
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
            dismiss_pending_review_requests(obj.pk)

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
                messages.success(request, _("Request deleted."))
                return redirect("admin:zetom_requestmain_changelist")
            messages.error(request, _("Reason is required."))

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

        context["status_choices"] = [(RequestStatus.cancelled, RequestStatus.cancelled.label)]
        has_obj = obj is not None and obj.pk is not None
        context["attachments"] = (
            list(obj.attachments.order_by("-uploaded_at")) if has_obj else []
        )
        context["ofertas"] = obj.oferta_set.order_by("-created_at") if has_obj else []
        context["zlecenia"] = obj.zlecenie_set.order_by("-created_at") if has_obj else []
        context["wnioski"] = obj.wniosek_set.order_by("-created_at") if has_obj else []
        context["history_entries"] = (
            obj.status_history.select_related("changed_by").order_by("-changed_at")
            if has_obj else []
        )
        # БАГ-2: полная история изменений полей через django-simple-history.
        # Диффы считаем здесь — в шаблоне нельзя вызывать методы с аргументами.
        if has_obj:
            field_history = []
            records = list(
                obj.history.select_related("history_user").order_by("-history_date")[:50]
            )
            for record in records:
                changes = []
                if record.prev_record:
                    delta = record.diff_against(record.prev_record)
                    changes = [
                        {"field": c.field, "old": c.old, "new": c.new}
                        for c in delta.changes
                    ]
                field_history.append({
                    "history_type": record.history_type,
                    "history_user": record.history_user,
                    "history_date": record.history_date,
                    "changes": changes,
                })
            context["field_history"] = field_history
        else:
            context["field_history"] = []
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
        context["can_change_request_status"] = user_has_perm(
            request.user, "change_request_status"
        )

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

        # claude — linked clients (M2M) + suggestions when none linked.
        # Add view: eligible_users_popup + departments_choices for popup step 04.
        if has_obj:
            context["linked_clients"] = list(obj.clients.all())
            # Show client suggestions in card only when no client linked yet.
            if not context["linked_clients"]:
                context["suggested_clients"] = find_candidates(obj)
            else:
                context["suggested_clients"] = []
        else:
            context["linked_clients"] = []
            context["suggested_clients"] = []
            # Add-form popup step 04 needs users + departments.
            from crm.zetom.admin.requestnull_validate import _eligible_users
            context["eligible_users_popup"] = _eligible_users()
            context["departments_choices"] = DepartmentsVariants.choices

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
            path(
                "<path:object_id>/link-client/",
                view(self.link_client_action),
                name="zetom_requestmain_link_client",
            ),
            path(
                "<path:object_id>/create-client/",
                view(self.create_client_action),
                name="zetom_requestmain_create_client",
            ),
            path(
                "<path:object_id>/unlink-client/<int:client_id>/",
                view(self.unlink_client_action),
                name="zetom_requestmain_unlink_client",
            ),
            path(
                "check-duplicates/",
                view(self.check_duplicates_action),
                name="zetom_requestmain_check_duplicates",
            ),
            path(
                "dup-request-action/",
                view(self.dup_request_action),
                name="zetom_requestmain_dup_request_action",
            ),
            path(
                "<path:object_id>/link-client-json/<int:client_id>/",
                view(self.link_client_json),
                name="zetom_requestmain_link_client_json",
            ),
            path(
                "<path:object_id>/unlink-client-json/<int:client_id>/",
                view(self.unlink_client_json),
                name="zetom_requestmain_unlink_client_json",
            ),
            path(
                "<path:object_id>/create-client-json/",
                view(self.create_client_json),
                name="zetom_requestmain_create_client_json",
            ),
            path(
                "<path:object_id>/upload-attachment/",
                view(self.upload_attachment_action),
                name="zetom_requestmain_upload_attachment",
            ),
            path(
                "<path:object_id>/delete-attachment/<int:attachment_id>/",
                view(self.delete_attachment_action),
                name="zetom_requestmain_delete_attachment",
            ),
            path(
                "<path:object_id>/edit-client-json/<int:client_id>/",
                view(self.edit_client_json),
                name="zetom_requestmain_edit_client_json",
            ),
            path(
                "<path:object_id>/save-client-json/<int:client_id>/",
                view(self.save_client_json),
                name="zetom_requestmain_save_client_json",
            ),
        ]
        return custom + urls

    # ---------- JSON client-link endpoints (for card JS) ----------

    def link_client_json(self, request, object_id, client_id):
        if request.method != "POST":
            return JsonResponse({"ok": False}, status=405)
        obj, denied = self._get_req_for_action(request, object_id, "edit_requests")
        if denied:
            return JsonResponse({"ok": False, "error": "permission"}, status=403)
        cl = Client.objects.filter(pk=client_id).first()
        if not cl:
            return JsonResponse({"ok": False, "error": "not found"}, status=404)
        _, created = RequestClientLink.objects.get_or_create(
            request=obj, client=cl, defaults={"linked_by": request.user}
        )
        return JsonResponse({"ok": True, "created": created, "label": str(cl), "pk": cl.pk, "nip": cl.company_nip or ""})

    def unlink_client_json(self, request, object_id, client_id):
        if request.method != "POST":
            return JsonResponse({"ok": False}, status=405)
        obj, denied = self._get_req_for_action(request, object_id, "edit_requests")
        if denied:
            return JsonResponse({"ok": False, "error": "permission"}, status=403)
        RequestClientLink.objects.filter(request=obj, client_id=client_id).delete()
        return JsonResponse({"ok": True})

    def create_client_json(self, request, object_id):
        if request.method != "POST":
            return JsonResponse({"ok": False}, status=405)
        obj, denied = self._get_req_for_action(request, object_id, "edit_requests")
        if denied:
            return JsonResponse({"ok": False, "error": "permission"}, status=403)
        cl = Client.objects.create(
            first_name=obj.first_name,
            last_name=obj.last_name,
            company_name=obj.company_name,
            company_nip=obj.company_nip or None,
            phone=obj.phone,
            email=obj.email,
            address=obj.address,
        )
        RequestClientLink.objects.create(request=obj, client=cl, linked_by=request.user)
        return JsonResponse({"ok": True, "label": str(cl), "pk": cl.pk, "nip": cl.company_nip or ""})

    def edit_client_json(self, request, object_id, client_id):
        """Returns client data in JSON format for inline editing in a modal."""
        if request.method != "GET":
            return JsonResponse({"ok": False}, status=405)
        obj, denied = self._get_req_for_action(request, object_id, "edit_requests")
        if denied:
            return JsonResponse({"ok": False, "error": "permission"}, status=403)
        cl = Client.objects.filter(pk=client_id).first()
        if not cl:
            return JsonResponse({"ok": False, "error": "not found"}, status=404)
        return JsonResponse({
            "ok": True,
            "pk": cl.pk,
            "first_name": cl.first_name or "",
            "last_name": cl.last_name or "",
            "company_name": cl.company_name or "",
            "company_nip": cl.company_nip or "",
            "phone": str(cl.phone) if cl.phone else "",
            "email": cl.email or "",
            "address": cl.address or "",
        })

    def save_client_json(self, request, object_id, client_id):
        """Saves client data from the modal form."""
        if request.method != "POST":
            return JsonResponse({"ok": False}, status=405)
        obj, denied = self._get_req_for_action(request, object_id, "edit_requests")
        if denied:
            return JsonResponse({"ok": False, "error": "permission"}, status=403)
        cl = Client.objects.filter(pk=client_id).first()
        if not cl:
            return JsonResponse({"ok": False, "error": "not found"}, status=404)
        
        # Update client fields
        cl.first_name = (request.POST.get("first_name") or "").strip() or None
        cl.last_name = (request.POST.get("last_name") or "").strip() or None
        cl.company_name = (request.POST.get("company_name") or "").strip() or None
        cl.company_nip = (request.POST.get("company_nip") or "").strip() or None
        phone_raw = (request.POST.get("phone") or "").strip()
        cl.phone = phone_raw or None
        cl.email = (request.POST.get("email") or "").strip() or None
        cl.address = (request.POST.get("address") or "").strip() or None

        try:
            cl.clean()  # normalizes NIP, no validate_unique side-effects
            cl.save(update_fields=[
                "first_name", "last_name", "company_name", "company_nip",
                "phone", "email", "address",
            ])
            return JsonResponse({
                "ok": True,
                "pk": cl.pk,
                "label": cl.short_label(),
                "nip": cl.company_nip or "",
                "first_name": cl.first_name or "",
                "last_name": cl.last_name or "",
                "company_name": cl.company_name or "",
                "company_nip": cl.company_nip or "",
                "phone": str(cl.phone) if cl.phone else "",
                "email": cl.email or "",
                "address": cl.address or "",
            })
        except Exception as e:
            return JsonResponse({
                "ok": False,
                "error": str(e)
            }, status=400)

    # ---------- Pre-save duplicate check (JSON, for the add-form popup) ----------

    # claude — JSON-эндпоинт: возвращает возможные дубликаты (клиенты + заявки)
    # для значений add-формы. JS-попап дёргает его при нажатии Save и, если
    # хоть что-то похоже, показывает предупреждение до отправки формы.
    def check_duplicates_action(self, request):
        probe = RequestMain(
            first_name=request.GET.get("first_name") or None,
            last_name=request.GET.get("last_name") or None,
            phone=request.GET.get("phone") or None,
            email=request.GET.get("email") or None,
            company_name=request.GET.get("company_name") or None,
            company_nip=request.GET.get("company_nip") or None,
        )
        items = []
        for c in find_candidates(probe):
            cl = c.client
            items.append({
                "type": "client",
                "pk": cl.pk,
                "label": str(cl),
                "first_name": cl.first_name or "",
                "last_name": cl.last_name or "",
                "company_name": cl.company_name or "",
                "company_nip": cl.company_nip or "",
                "phone": str(cl.phone) if cl.phone else "",
                "email": cl.email or "",
                "score": c.score,
                "badges": [[b.kind, str(b.label)] for b in c.badges],
                "highlights": {k: True for k in c.highlights},
                "url": reverse("admin:clients_client_change", args=[cl.pk]),
            })
        for d in find_request_duplicates(probe):
            name = d.obj.full_name or "—"
            if d.obj.company_name:
                name = f"{name} · {d.obj.company_name}"
            items.append({
                "type": d.kind,
                "pk": d.obj.pk,
                "label": f"#{d.obj.pk} {name}",
                "first_name": d.obj.first_name or "",
                "last_name": d.obj.last_name or "",
                "company_name": d.obj.company_name or "",
                "phone": str(d.obj.phone) if d.obj.phone else "",
                "email": d.obj.email or "",
                "score": d.score,
                "badges": [[b.kind, str(b.label)] for b in d.badges],
                "strong": d.is_strong,
                "url": (
                    reverse("admin:zetom_requestmain_change", args=[d.obj.pk])
                    if d.kind == "main" else None
                ),
            })
        return JsonResponse({"count": len(items), "items": items})

    # claude — generic duplicate-request action for the add-form popup
    # (no new RequestMain pk needed — acts on existing records only).
    def dup_request_action(self, request):
        if request.method != "POST":
            return JsonResponse({"ok": False, "error": "POST required"}, status=405)
        from crm.status_manager.services.status_service import (
            cancel_request as _cancel,
        )
        from crm.zetom.models import RequestNull as RN
        from crm.zetom.services.request_duplicate_finder import KIND_NULL

        # claude — soft-delete one existing duplicate, type-aware:
        # RequestMain → soft-cancel (auditable); RequestNull → safedelete soft
        # (SOFT_DELETE_CASCADE → trash). Both recoverable. Returns error string
        # or None.
        def _soft_delete_existing(kind, pk):
            if kind == KIND_NULL:
                obj = RN.objects.filter(pk=pk).first()
                if obj:
                    obj.delete()  # default policy = SOFT_DELETE_CASCADE → trash
            else:
                obj = RequestMain.objects.filter(pk=pk).first()
                if obj:
                    try:
                        _cancel(obj, request.user,
                                reason=_("Cancelled as duplicate from the add form."))
                    except ValueError as exc:
                        return str(exc)
            return None

        action = request.POST.get("action", "")

        # Bulk: soft-delete every rendered duplicate. The popup JS posts the
        # "<kind>:<pk>" identifiers it already has as repeated `targets` values.
        if action == "delete_all_dupes":
            count = 0
            for raw in request.POST.getlist("targets"):
                kind, _sep, raw_pk = raw.partition(":")
                try:
                    pk = int(raw_pk)
                except ValueError:
                    continue
                _soft_delete_existing(kind, pk)
                count += 1
            return JsonResponse({"ok": True, "count": count})

        if ":" not in action:
            return JsonResponse({"ok": False, "error": "bad action"}, status=400)
        op, kind, raw_pk = (action.split(":", 2) + ["", ""])[:3]
        try:
            pk = int(raw_pk)
        except ValueError:
            return JsonResponse({"ok": False, "error": "bad pk"}, status=400)
        if op == "delete_existing":
            err = _soft_delete_existing(kind, pk)
            if err:
                return JsonResponse({"ok": False, "error": err}, status=400)
            return JsonResponse({"ok": True})
        return JsonResponse({"ok": False, "error": "unknown op"}, status=400)

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

    # ---------- Client link actions ----------

    # claude — привязка существующего Client к заявке (M2M через
    # RequestClientLink). Идемпотентно: повторный линк не дублируется.
    def link_client_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)
        obj, denied = self._get_req_for_action(request, object_id, "edit_requests")
        if denied is not None:
            return denied

        client_id = request.POST.get("client_id")
        client = Client.objects.filter(pk=client_id).first()
        if client is None:
            messages.error(request, _("Client not found."))
            return redirect("admin:zetom_requestmain_change", object_id)

        _link, created = RequestClientLink.objects.get_or_create(
            request=obj, client=client, defaults={"linked_by": request.user},
        )
        if created:
            messages.success(request, _("Linked client %(c)s.") % {"c": client})
        else:
            messages.info(request, _("Client already linked."))
        return redirect("admin:zetom_requestmain_change", object_id)

    # claude — создать нового Client из данных заявки и сразу привязать.
    def create_client_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)
        obj, denied = self._get_req_for_action(request, object_id, "edit_requests")
        if denied is not None:
            return denied

        client = Client.objects.create(
            first_name=obj.first_name,
            last_name=obj.last_name,
            company_name=obj.company_name,
            company_nip=obj.company_nip or None,
            phone=obj.phone,
            email=obj.email,
            address=obj.address,
        )
        RequestClientLink.objects.create(
            request=obj, client=client, linked_by=request.user,
        )
        messages.success(request, _("Created and linked client %(c)s.") % {"c": client})
        return redirect("admin:zetom_requestmain_change", object_id)

    def unlink_client_action(self, request, object_id, client_id):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)
        obj, denied = self._get_req_for_action(request, object_id, "edit_requests")
        if denied is not None:
            return denied

        deleted, _n = RequestClientLink.objects.filter(
            request=obj, client_id=client_id
        ).delete()
        if deleted:
            messages.success(request, _("Client unlinked."))
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

    # ---------- File attachment actions ----------

    def upload_attachment_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)
        obj, denied = self._get_req_for_action(request, object_id, "edit_requests")
        if denied is not None:
            return denied
        files = request.FILES.getlist("attachments")
        if not files:
            messages.error(request, _("No files selected."))
            return redirect("admin:zetom_requestmain_change", object_id)
        for f in files:
            RequestAttachment.objects.create(
                request_main=obj, file=f, uploaded_by=request.user
            )
        messages.success(request, _("%(n)d file(s) uploaded.") % {"n": len(files)})
        return redirect("admin:zetom_requestmain_change", object_id)

    def delete_attachment_action(self, request, object_id, attachment_id):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)
        obj, denied = self._get_req_for_action(request, object_id, "edit_requests")
        if denied is not None:
            return denied
        att = RequestAttachment.objects.filter(pk=attachment_id, request_main=obj).first()
        if att:
            att.file.delete(save=False)
            att.delete()
            messages.success(request, _("Attachment deleted."))
        return redirect("admin:zetom_requestmain_change", object_id)
