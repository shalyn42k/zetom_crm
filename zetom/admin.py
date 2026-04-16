from django.contrib import admin
from django.shortcuts import redirect
from unfold.admin import ModelAdmin
from unfold.decorators import action
from .forms import AddOferta, AddRequestFormMain, AddRequestFormNull
from .models import Oferta, RequestMain, RequestNull, Role, UserProfile
from users.admin import get_profile




# =========================================================
# RequestNull
# =========================================================
@admin.register(RequestNull)
class RequestNullAdmin(ModelAdmin):
    form = AddRequestFormNull
    list_display = ("created_at", "phone", "company_name", "company_nip", "email")
    actions_detail = ["oferta_action", "zlecenie_action"]

    def has_module_permission(self, request):
        if request.user.is_superuser:
            return True

        profile = get_profile(request.user)
        if not profile:
            return False

        # Проверяем, может ли пользователь видеть модуль AND модель не скрыта
        can_see = profile.can_see_module("requests")
        is_hidden = profile.is_model_hidden("requestnull")
        
        return can_see and not is_hidden

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True

        profile = get_profile(request.user)
        if not profile:
            print(f"❌ RequestNull: NO PROFILE for user {request.user}")
            return False

        can_see = profile.can_see_module("requests")
        print(f"✓ RequestNull: {profile.user.username} role={profile.role}, can_see={can_see}")
        return can_see

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True

        profile = get_profile(request.user)
        if not profile:
            return False

        return profile.can_edit_model("requestnull")

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser:
            return []

        profile = get_profile(request.user)
        if profile and profile.is_model_readonly("requestnull"):
            return [f.name for f in self.model._meta.fields]

        return super().get_readonly_fields(request, obj)

    @action(description="Oferta", icon="assignment", url_path="oferta")
    def oferta_action(self, request, object_id):
        return redirect("admin:zetom_requestnull_change", object_id)

    @action(description="Zlecenie", icon="assignment", url_path="zlecenie_action")
    def zlecenie_action(self, request, object_id):
        return redirect("admin:zetom_requestnull_change", object_id)


# =========================================================
# RequestMain
# =========================================================
@admin.register(RequestMain)
class RequestMainAdmin(ModelAdmin):
    form = AddRequestFormMain
    list_display = ("created_at", "full_name", "address", "notes")
    exclude = ["from_null"]

    def has_module_permission(self, request):
        if request.user.is_superuser:
            return True

        profile = get_profile(request.user)
        if not profile:
            return False

        # Проверяем, может ли пользователь видеть модуль AND модель не скрыта
        can_see = profile.can_see_module("requests")
        is_hidden = profile.is_model_hidden("requestmain")
        
        return can_see and not is_hidden

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True

        profile = get_profile(request.user)
        if not profile:
            print(f"❌ RequestMain: NO PROFILE for user {request.user}")
            return False

        can_see = profile.can_see_module("requests")
        print(f"✓ RequestMain: {profile.user.username} role={profile.role}, can_see={can_see}")
        return can_see

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True

        profile = get_profile(request.user)
        if not profile:
            return False

        return profile.can_edit_model("requestmain")

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser:
            return []

        profile = get_profile(request.user)
        if profile and profile.is_model_readonly("requestmain"):
            return [f.name for f in self.model._meta.fields]

        return super().get_readonly_fields(request, obj)


# =========================================================
# Oferta
# =========================================================
@admin.register(Oferta)
class OfertaAdmin(ModelAdmin):
    form = AddOferta
    list_display = ("created_at", "price")
    exclude = ["from_main"]

    def has_module_permission(self, request):
        if request.user.is_superuser:
            return True

        profile = get_profile(request.user)
        if not profile:
            return False

        # Проверяем, может ли пользователь видеть модуль AND модель не скрыта
        can_see = profile.can_see_module("requests")
        is_hidden = profile.is_model_hidden("oferta")
        
        return can_see and not is_hidden

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True

        profile = get_profile(request.user)
        if not profile:
            print(f"❌ Oferta: NO PROFILE for user {request.user}")
            return False

        can_see = profile.can_see_module("requests")
        print(f"✓ Oferta: {profile.user.username} role={profile.role}, can_see={can_see}")
        return can_see

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True

        profile = get_profile(request.user)
        if not profile:
            return False

        return profile.can_edit_model("oferta")

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser:
            return []

        profile = get_profile(request.user)
        if profile and profile.is_model_readonly("oferta"):
            return [f.name for f in self.model._meta.fields]

        return super().get_readonly_fields(request, obj)



