from django.contrib import admin
from .models import Record, Role, UserProfile

@admin.register(Record)
class RecordAdmin(admin.ModelAdmin):
    list_display = (
        'created_at', 'first_name', 'last_name', 'email',
        'phone', 'address', 'city', 'state', 'zipcode'
    )
    search_fields = ('first_name', 'last_name')

admin.site.register(Role)
admin.site.register(UserProfile)
