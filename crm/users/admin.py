from django.contrib import admin
from unfold.admin import ModelAdmin

from crm.users.models import Role, UserProfile


@admin.register(Role)
class AdminRole(ModelAdmin):
    list_display = ("code", "name", "level")


@admin.register(UserProfile)
class AdminUserProfile(ModelAdmin):
    list_display = ("user", "role")
