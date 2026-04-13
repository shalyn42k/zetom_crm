from django import forms
from django.contrib import admin
from django.shortcuts import redirect
from unfold.admin import ModelAdmin
from unfold.decorators import action
from unfold.enums import ActionVariant

from .forms import AddOferta, AddRequestFormMain, AddRequestFormNull
from .models import Oferta, RequestMain, RequestNull, Role, UserProfile

class ActionVariant(enumerate):
     DEFAULT = "default"
     PRIMARY = "primary"
     SUCCESS = "success"
     INFO = "info"
     WARNING = "warning"
     DANGER = "danger"


@admin.register(Role)
class AdminRole(ModelAdmin):
    list_display = ("code", "name", "level")

@admin.register(UserProfile)
class AdminUserProfile(ModelAdmin):
    list_display = ("user", "role")


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
    def approve_action(self, request, object_id):
        return redirect("admin:zetom_requestmain_change", object_id)


@admin.register(RequestMain)
class RequestMainAdmin(ModelAdmin):
    form = AddRequestFormMain
    list_display = ("created_at", "company_name")
    fields = ("from_null", "full_name", "phone", "company_name", "company_nip", "email", "address", "notes")
    #exclude = ["from_null"]
    actions_detail = ["oferta_action", "zlecenie_action"]

    @action(
        description="Oferta",
        icon="assignment",
        url_path="oferta",
    )
    def oferta_action(self, request, object_id):
        self.message_user(request, "Oferta")
        return redirect("admin:zetom_oferta_change", object_id)

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
    fields = ("from_main", "phone", "email", "company_name", "company_nip", "price")
   # exclude = ["from_main"]
