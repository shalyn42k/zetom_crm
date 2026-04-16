# Django imports
from django import forms
from django.contrib import admin, messages
from django.contrib.admin.models import LogEntry
from django.db import transaction
from django.shortcuts import redirect

# Unfold imports
from unfold.admin import ModelAdmin
from unfold.decorators import action
from unfold.enums import ActionVariant

# Notification app imports
from notification.services.notification_service import send_notification_approve_null
from users.admin import get_profile

# Users app imports
from users.models import Role, UserProfile

# Zetom app imports
from zetom.forms import AddOferta, AddRequestFormMain, AddRequestFormNull
from zetom.models import Oferta, RequestMain, RequestNull
from zetom.services.request_service import approve_null_action, approve_oferta_action

# Other imports


# Ии написал класс, ебу че делает
@admin.register(LogEntry)
class LogEntryAdmin(ModelAdmin):  # Используем ModelAdmin от Unfold для красоты
    list_display = ("action_time", "user", "content_type", "object_repr", "action_flag")
    list_filter = ("action_flag", "content_type", "user")
    search_fields = ("object_repr", "change_message")

    # Запрещаем всё, кроме просмотра
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RequestNull)
class RequestNullAdmin(ModelAdmin):
    form = AddRequestFormNull
    list_display = ("created_at", "phone", "company_name", "company_nip", "email")
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


@admin.register(RequestMain)
class RequestMainAdmin(ModelAdmin):
    form = AddRequestFormMain
    # change_form_template = ""
    list_display = ("created_at", "company_name")
    fields = (
        "full_name",
        "phone",
        "company_name",
        "company_nip",
        "email",
        "address",
        "notes",
    )
    actions_detail = ["oferta_action", "zlecenie_action"]
    warn_unsaved_form = True

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
        print(
            f"✓ RequestNull: {profile.user.username} role={profile.role}, can_see={can_see}"
        )
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
        oferta = approve_oferta_action(object_id)
        messages.info(request, f"Redirecting to Oferta: {object_id}")
        return redirect("admin:zetom_oferta_change", oferta.pk)

    @action(description="Zlecenie", icon="assignment", url_path="zlecenie_action")
    def zlecenie_action(self, request, object_id):
        self.message_user(request, "no zlecenie :(")
        return redirect("admin:zetom_requestmain_change", object_id)


@admin.register(Oferta)
class OfertaAdmin(ModelAdmin):
    form = AddOferta
    list_display = ("created_at", "company_name")
    readonly_fields = ("from_main",)
    fields = ("from_main", "phone", "email", "company_name", "company_nip", "price")
    warn_unsaved_form = True

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
        print(
            f"✓ Oferta: {profile.user.username} role={profile.role}, can_see={can_see}"
        )
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
