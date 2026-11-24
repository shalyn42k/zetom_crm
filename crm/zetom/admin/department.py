from django.contrib import admin
from unfold.admin import ModelAdmin as UnfoldModelAdmin

from crm.users.models import UserProfile
from crm.users.utils import user_has_perm
from crm.zetom.forms import DepartmentForm
from crm.zetom.models import Department

# Every UserProfile list that may hold a department code. main_ and head_of_
# must stay subsets of departments (UserProfile.clean), so un-assigning a
# person has to strip the code from all three.
_PROFILE_DEPT_FIELDS = ("departments", "main_departments", "head_of_departments")


@admin.register(Department)
class DepartmentAdmin(UnfoldModelAdmin):
    form = DepartmentForm
    list_display = ("name",)
    fields = ("name", "users")

    # claude — same RBAC gates as the Users admin (the sidebar link is shown
    # on view_users); without them only superusers got past Django's model
    # perms, which nobody is granted. Delete is superuser-only: requests and
    # profiles keep the code, so a deleted department would show as a raw
    # DEPARTMENT_<id>.
    def has_module_permission(self, request):
        return user_has_perm(request.user, "view_users")

    def has_view_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_users")

    def has_add_permission(self, request):
        return user_has_perm(request.user, "edit_users")

    def has_change_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_users")

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def save_model(self, request, obj, form, change):
        # Saves the department first: a new one only gets its code here.
        super().save_model(request, obj, form, change)
        users = form.cleaned_data["users"]

        # Assign: add the code to everyone ticked who doesn't have it yet.
        for user in users:
            profile = user.profile
            if obj.code not in profile.departments:
                profile.departments.append(obj.code)
                profile.save(update_fields=["departments"])

        # Un-assign: drop the code from everyone who has it but was unticked.
        for profile in UserProfile.objects.filter(departments__contains=[obj.code]):
            if profile.user in users:
                continue
            for field in _PROFILE_DEPT_FIELDS:
                codes = getattr(profile, field)
                if obj.code in codes:
                    codes.remove(obj.code)
            profile.save(update_fields=list(_PROFILE_DEPT_FIELDS))
