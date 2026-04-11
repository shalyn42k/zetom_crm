from django import forms
from django.contrib import admin
from django.shortcuts import redirect
from unfold.admin import ModelAdmin
from unfold.decorators import action

from .forms import AddOferta, AddRequestFormMain, AddRequestFormNull
from .models import Oferta, RequestMain, RequestNull, Role, UserProfile


@admin.register(Role)
class AdminRole(admin.ModelAdmin):
    list_display = ("code", "name", "level")

@admin.register(UserProfile)
class AdminUserProfile(admin.ModelAdmin):
    list_display = ("user", "role")


@admin.register(RequestNull)
class RequestNullAdmin(admin.ModelAdmin):
    form = AddRequestFormNull
    list_display = ("created_at", "phone", "company_name", "company_nip", "email")
    actions_detail = ["oferta_action", "zlecenie_action"]

    @action(
        description="Oferta",
        icon="assignment",
        url_path="oferta",
    )
    def oferta_action(self, request, object_id):
        self.message_user(request, "Oferta")
        return redirect("admin:zetom_request_null_change", object_id)

    @action(
        description="zlecenie",
        icon="assignment",
        url_path="zlecenie_action",
    )
    def zlecenie_action(self, request, object_id):
        self.message_user(request, "zlecenie")
        return redirect("admin:zetom_request_null_change", object_id)


@admin.register(RequestMain)
class RequestMainAdmin(admin.ModelAdmin):
    form = AddRequestFormMain
    list_display = ("created_at", "full_name", "address", "notes")
    exclude = ["from_null"]


@admin.register(Oferta)
class OfertaAdmin(admin.ModelAdmin):
    form = AddOferta
    list_display = ("created_at", "price")
    exclude = ["from_main"]
