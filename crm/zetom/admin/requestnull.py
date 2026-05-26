"""Validation Window admin — public form intake records.

Add view is disabled — RequestNull instances come exclusively from the
public site form (crm.zetom.views.email_template).

The standard Django change-view is replaced by the Validation Window
(see requestnull_validate.ValidationWindowMixin): clicking a row in
the changelist redirects straight to the 3-zone validation screen
instead of the generic ModelForm.
"""
from django.contrib import admin
from django.shortcuts import redirect

from crm.zetom.forms import AddRequestFormNull
from crm.zetom.models import RequestNull

from .base import BaseRequestAdmin
# claude
from .requestnull_validate import ValidationWindowMixin


# claude
@admin.register(RequestNull)
class RequestNullAdmin(ValidationWindowMixin, BaseRequestAdmin):
    form = AddRequestFormNull
    list_display = ("created_at", "updated_at", "company_name", "source")
    list_filter = ("source",)

    def has_add_permission(self, request):
        return False

    # claude — RequestNull has no editable change-view anymore; every entry
    # goes through the Validation Window. We override change_view to redirect
    # so the changelist row-click lands directly on /validate/ rather than
    # the generic ModelForm.
    def change_view(self, request, object_id, form_url="", extra_context=None):
        return redirect("admin:zetom_requestnull_validate", object_id=object_id)
