"""Mixin with the HTMX-driven department actions used by CustomUserAdmin.

Lives in a separate module so the main admin class in `user.py` stays
focused on identity / role / password concerns. The mixin contributes:

  - get_urls()    : five admin routes under /admin/auth/user/<id>/departments/
  - _build_dept_context() : builds my_departments / available_departments
    structures consumed by `_partials/tab_departments.html`
  - five `*_department_action` methods returning the tab partial as
    an HTMX fragment

Routing convention mirrors zetom/admin/requestmain.py (custom urls
prepended in `get_urls`, names prefixed with the model's admin-url label).
"""
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.translation import gettext_lazy as _

from crm.users.models import UserProfile
from crm.zetom.models import DepartmentsVariants


# claude
class DepartmentActionsMixin:
    """Adds department-tab HTMX endpoints to a User ModelAdmin."""

    # ---------- URL wiring ----------

    def get_urls(self):
        urls = super().get_urls()
        view = self.admin_site.admin_view
        custom = [
            path(
                "<int:object_id>/departments/add/",
                view(self.add_department_action),
                name="auth_user_add_department",
            ),
            path(
                "<int:object_id>/departments/<str:dept_code>/remove/",
                view(self.remove_department_action),
                name="auth_user_remove_department",
            ),
            path(
                "<int:object_id>/departments/<str:dept_code>/promote/",
                view(self.promote_department_action),
                name="auth_user_promote_department",
            ),
            path(
                "<int:object_id>/departments/<str:dept_code>/demote/",
                view(self.demote_department_action),
                name="auth_user_demote_department",
            ),
            # claude
            path(
                "<int:object_id>/departments/<str:dept_code>/grant-head/",
                view(self.grant_head_department_action),
                name="auth_user_grant_head_department",
            ),
            # claude
            path(
                "<int:object_id>/departments/<str:dept_code>/revoke-head/",
                view(self.revoke_head_department_action),
                name="auth_user_revoke_head_department",
            ),
            path(
                "<int:object_id>/departments/search/",
                view(self.search_departments_action),
                name="auth_user_search_departments",
            ),
        ]
        return custom + urls

    # claude
    def _can_grant_head(self, request):
        """Only superusers and users with role.code == 'admin' may toggle headship."""
        if request.user.is_superuser:
            return True
        prof = getattr(request.user, "profile", None)
        return bool(prof and prof.is_role("admin"))

    # ---------- Context builder ----------

    def _build_dept_context(self, request, user):
        profile = getattr(user, "profile", None)
        assigned_codes = list(profile.departments) if profile and profile.departments else []
        main_codes = set(profile.main_departments) if profile and profile.main_departments else set()
        # claude
        head_codes = set(profile.head_of_departments) if profile and profile.head_of_departments else set()
        dept_labels = dict(DepartmentsVariants.choices)

        members_by_code: dict[str, list[dict]] = {}
        if assigned_codes:
            teammates = (
                User.objects.filter(profile__departments__overlap=assigned_codes)
                .select_related("profile__role")
                .order_by("first_name", "last_name", "username")
            )
            for tm in teammates:
                # claude — headship теперь берётся из head_of_departments, а не из main_departments
                tm_head = set(tm.profile.head_of_departments or [])
                for code in (tm.profile.departments or []):
                    if code not in assigned_codes:
                        continue
                    first_initial = (tm.first_name[:1] if tm.first_name else tm.username[:1]).upper()
                    members_by_code.setdefault(code, []).append({
                        "full_name": tm.get_full_name() or tm.username,
                        "initials": first_initial,
                        "role_label": tm.profile.role.name if tm.profile.role else "",
                        "is_head": code in tm_head,
                        "is_you": tm.pk == request.user.pk,
                    })

        # Sort each department's member list: head → you → others.
        for members in members_by_code.values():
            members.sort(key=lambda m: (0 if m["is_head"] else (1 if m["is_you"] else 2)))

        my_departments = [
            {
                "code": code,
                "label": dept_labels.get(code, code),
                "is_primary": code in main_codes,
                # claude
                "is_head": code in head_codes,
                "members": members_by_code.get(code, []),
            }
            for code in assigned_codes
        ]

        available_departments = [
            {"code": code, "label": label}
            for code, label in DepartmentsVariants.choices
            if code not in assigned_codes
        ]

        return {
            "my_departments": my_departments,
            "available_departments": available_departments,
            # claude
            "can_grant_head": self._can_grant_head(request),
        }

    def _render_dept_tab(self, request, user):
        ctx = {"original": user, **self._build_dept_context(request, user)}
        return TemplateResponse(
            request,
            "admin/auth/user/_partials/tab_departments.html",
            ctx,
        )

    # ---------- Action endpoints ----------

    def add_department_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:auth_user_change", object_id)
        user = get_object_or_404(User, pk=object_id)
        code = request.POST.get("code")
        if code not in DepartmentsVariants.values:
            return HttpResponseBadRequest("Invalid department code")
        profile, _created = UserProfile.objects.get_or_create(user=user)
        if code not in (profile.departments or []):
            profile.departments = list(profile.departments or []) + [code]
            profile.save(update_fields=["departments"])
        return self._render_dept_tab(request, user)

    def remove_department_action(self, request, object_id, dept_code):
        if request.method not in ("POST", "DELETE"):
            return redirect("admin:auth_user_change", object_id)
        user = get_object_or_404(User, pk=object_id)
        if dept_code not in DepartmentsVariants.values:
            return HttpResponseBadRequest("Invalid department code")
        profile, _created = UserProfile.objects.get_or_create(user=user)
        # Safety: removing a primary department would invalidate the
        # main_departments ⊆ departments invariant. Demote it first.
        if dept_code in (profile.main_departments or []):
            messages.error(
                request,
                _("Demote this department from primary before removing."),
            )
            return self._render_dept_tab(request, user)
        # claude — same invariant for head_of_departments ⊆ departments
        if dept_code in (profile.head_of_departments or []):
            messages.error(
                request,
                _("Revoke head status for this department before removing."),
            )
            return self._render_dept_tab(request, user)
        if dept_code in (profile.departments or []):
            profile.departments = [c for c in profile.departments if c != dept_code]
            profile.save(update_fields=["departments"])
        return self._render_dept_tab(request, user)

    def promote_department_action(self, request, object_id, dept_code):
        if request.method != "POST":
            return redirect("admin:auth_user_change", object_id)
        user = get_object_or_404(User, pk=object_id)
        if dept_code not in DepartmentsVariants.values:
            return HttpResponseBadRequest("Invalid department code")
        profile, _created = UserProfile.objects.get_or_create(user=user)
        if dept_code not in (profile.departments or []):
            return HttpResponseBadRequest("User does not belong to this department")
        if dept_code not in (profile.main_departments or []):
            profile.main_departments = list(profile.main_departments or []) + [dept_code]
            profile.save(update_fields=["main_departments"])
        return self._render_dept_tab(request, user)

    def demote_department_action(self, request, object_id, dept_code):
        if request.method != "POST":
            return redirect("admin:auth_user_change", object_id)
        user = get_object_or_404(User, pk=object_id)
        if dept_code not in DepartmentsVariants.values:
            return HttpResponseBadRequest("Invalid department code")
        profile, _created = UserProfile.objects.get_or_create(user=user)
        if dept_code in (profile.main_departments or []):
            profile.main_departments = [c for c in profile.main_departments if c != dept_code]
            profile.save(update_fields=["main_departments"])
        return self._render_dept_tab(request, user)

    # claude
    def grant_head_department_action(self, request, object_id, dept_code):
        if request.method != "POST":
            return redirect("admin:auth_user_change", object_id)
        if not self._can_grant_head(request):
            return HttpResponseBadRequest("Only admins can grant head status")
        user = get_object_or_404(User, pk=object_id)
        if dept_code not in DepartmentsVariants.values:
            return HttpResponseBadRequest("Invalid department code")
        profile, _created = UserProfile.objects.get_or_create(user=user)
        if dept_code not in (profile.departments or []):
            return HttpResponseBadRequest("User does not belong to this department")
        if dept_code not in (profile.head_of_departments or []):
            profile.head_of_departments = list(profile.head_of_departments or []) + [dept_code]
            profile.save(update_fields=["head_of_departments"])
        return self._render_dept_tab(request, user)

    # claude
    def revoke_head_department_action(self, request, object_id, dept_code):
        if request.method != "POST":
            return redirect("admin:auth_user_change", object_id)
        if not self._can_grant_head(request):
            return HttpResponseBadRequest("Only admins can revoke head status")
        user = get_object_or_404(User, pk=object_id)
        if dept_code not in DepartmentsVariants.values:
            return HttpResponseBadRequest("Invalid department code")
        profile, _created = UserProfile.objects.get_or_create(user=user)
        if dept_code in (profile.head_of_departments or []):
            profile.head_of_departments = [c for c in profile.head_of_departments if c != dept_code]
            profile.save(update_fields=["head_of_departments"])
        return self._render_dept_tab(request, user)

    def search_departments_action(self, request, object_id):
        user = get_object_or_404(User, pk=object_id)
        query = (request.GET.get("q") or "").strip().lower()
        ctx = self._build_dept_context(request, user)
        if query:
            ctx["available_departments"] = [
                d for d in ctx["available_departments"]
                if query in d["label"].lower() or query in d["code"].lower()
            ]
        ctx["original"] = user
        return TemplateResponse(
            request,
            "admin/auth/user/_partials/_dept_search_results.html",
            ctx,
        )
