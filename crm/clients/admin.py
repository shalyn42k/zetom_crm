from django.contrib import admin

from crm.users.utils import user_has_perm

from .models import Client, ClientInteraction


# БАГ-9 + БАГ-10: inline история контактов прямо в карточке клиента
class ClientInteractionInline(admin.TabularInline):
    model = ClientInteraction
    extra = 0
    fields = ("contacted_at", "channel", "contact_person", "contacted_by", "summary", "request")
    autocomplete_fields = ("request",)
    readonly_fields = ("created_at",)
    ordering = ("-contacted_at",)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "company_name", "email", "phone")
    search_fields = ("first_name", "last_name", "company_name", "email", "phone")
    inlines = [ClientInteractionInline]

    # claude — раньше тут не было гейтов: любой is_staff видел и менял
    # базу клиентов. Привязываем к RBAC-кодам view_clients / edit_clients
    # (см. crm/users/signals.py). superuser получает всё через user_has_perm.
    def has_module_permission(self, request):
        return user_has_perm(request.user, "view_clients")

    def has_view_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_clients")

    def has_add_permission(self, request):
        return user_has_perm(request.user, "edit_clients")

    def has_change_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_clients")

    def has_delete_permission(self, request, obj=None):
        return user_has_perm(request.user, "delete_clients")


# БАГ-9 + БАГ-10: отдельный раздел для просмотра всех контактов
@admin.register(ClientInteraction)
class ClientInteractionAdmin(admin.ModelAdmin):
    list_display = ("contacted_at", "client", "channel", "contact_person", "contacted_by", "request")
    list_filter = ("channel",)
    search_fields = ("client__first_name", "client__last_name", "client__company_name", "summary", "contact_person")
    autocomplete_fields = ("client", "request")
    readonly_fields = ("created_at",)
    date_hierarchy = "contacted_at"