from django import forms
from django.contrib import admin

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
