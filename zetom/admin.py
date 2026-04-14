from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect
from unfold.admin import ModelAdmin
from unfold.decorators import action
from unfold.enums import ActionVariant


from .forms import AddOferta, AddRequestFormMain, AddRequestFormNull
from .models import Oferta, RequestMain, RequestNull, Role, UserProfile
from .services.request_service import approve_null_action, approve_oferta_action

@admin.register(Role)
class AdminRole(ModelAdmin):
    list_display = ("code", "name", "level")

@admin.register(UserProfile)
class AdminUserProfile(ModelAdmin):
    list_display = ("user", "role")


@admin.register(RequestNull)
class RequestNullAdmin(ModelAdmin):
    form = AddRequestFormNull
    list_display = (
        "created_at",
        "phone",
        "company_name",
        "company_nip",
        "email"
        )
    actions_detail = ["approve_action"]

    @action(
        description="Approve",
        variant=ActionVariant.SUCCESS,
        icon="",
    )
    def approve_action(self, request, object_id):
        new_main_record = approve_null_action(object_id)

        return redirect("admin:zetom_requestmain_change", object_id)


@admin.register(RequestMain)
class RequestMainAdmin(ModelAdmin):
    form = AddRequestFormMain
    list_display = ("created_at", "company_name")
    fields = ("full_name", "phone", "company_name", "company_nip", "email", "address", "notes")
    actions_detail = ["oferta_action", "zlecenie_action"]

    @action(
        description="Oferta",
        icon="assignment",
        url_path="oferta",
    )
    def oferta_action(self, request, object_id):
        oferta = approve_oferta_action(object_id)

        messages.info(request, f"Redirecting to Oferta: {object_id}")
    
        return redirect("admin:zetom_oferta_change", oferta.pk)

    @action(
        description="Zlecenie",
        icon="assignment",
        url_path="zlecenie_action",
    )
    def zlecenie_action(self, request, object_id):
        self.message_user(request, "Zlecenie")
        return redirect("admin:zetom_requestmain_change", object_id)

 
@admin.register(Oferta)
class OfertaAdmin(ModelAdmin):
    form = AddOferta
    list_display = ("created_at", "company_name")
    readonly_fields = ("from_main",)
    fields = ("from_main", "phone", "email", "company_name", "company_nip", "price")
