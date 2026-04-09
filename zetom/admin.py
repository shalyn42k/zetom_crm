from django.contrib import admin
from .models import Request_Null

@admin.register(Request_Null)
class Request_Null(admin.ModelAdmin):
    list_display = ('created_at', 'phone', 'company_name', 'company_nip', 'email')