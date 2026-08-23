from django import forms
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from crm.clients.models import Client


# claude — this widget replaced a plain forms.Select over Client.objects.all().
# That select rendered one <option> per person in the base — contacts of every
# firm included — into the request form on every page load: 50 contacts meant
# 51 options, and it grew linearly with the client base.
#
# Contract for the Requests redesign — keep these three things and the markup
# around them is free to change:
#   * a hidden input named/id'd `client` holds the selected client's pk. It
#     keeps the id `id_client` on purpose: requestmain_client_link.js reads
#     `getElementById("id_client").value` to build the "Link" M2M call, and a
#     hidden input answers `.value` exactly like the old select did.
#   * the visible box carries `data-client-picker`; client_picker.js binds to
#     that attribute, not to a class, an id, or a position in the DOM.
#   * picking a row fills `#id_first_name`/`#id_last_name`/`#id_company_name`/
#     `#id_company_nip`/`#id_email`/`#id_phone`/`#id_address` when present —
#     each one guarded, so dropping a field from the form breaks nothing.
#
# Styling is deliberately left to the page: no classes of our own beyond the
# hook attribute, nothing for a redesign to have to undo.
class ClientPickerWidget(forms.Widget):
    def render(self, name, value, attrs=None, renderer=None):
        pk = "" if value is None else value
        return format_html(
            '<input type="text" data-client-picker data-target="{id}" '
            'placeholder="{placeholder}" autocomplete="off">'
            '<input type="hidden" name="{name}" id="{id}" value="{pk}">',
            id="id_%s" % name,
            name=name,
            pk=pk,
            placeholder=_("Szukaj klienta — nazwisko, firma lub NIP…"),
        )


class ClientField(forms.ModelChoiceField):
    """Form-only picker: prefills the request's contact snapshot and feeds the
    "Link" button. Never saved — the persisted relation is the clients M2M."""

    def __init__(self, *args, **kwargs):
        super().__init__(
            # claude — the queryset is no longer iterated for rendering (the
            # widget draws no options); it only resolves the submitted pk on
            # clean, which is a single indexed lookup.
            queryset=Client.objects.all(),
            required=False,
            label=_("Client"),
            widget=ClientPickerWidget(),
            *args,
            **kwargs
        )
