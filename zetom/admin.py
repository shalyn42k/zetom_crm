from django import forms
from django.contrib import admin
from django.shortcuts import redirect

from unfold.admin import ModelAdmin
from unfold.decorators import action

from .models import Request_Null


@admin.register(Request_Null)
class Request_NullAdmin(ModelAdmin):      
    list_display = ('created_at', 'phone', 'company_name', 'company_nip', 'email')

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