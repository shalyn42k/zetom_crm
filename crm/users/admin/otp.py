# claude
"""Polish (translatable) labels for the 2FA device admin pages.

django-otp ships no Polish catalog and its model labels/help texts aren't
wrapped in gettext, so the superuser-only device pages stayed English.
Changing the model fields themselves would make makemigrations want a
migration in the third-party app, so the labels are swapped on the admin
form instead: the same django-otp admin classes, re-registered with a
get_form that sets translated labels and help texts.
"""
import copy

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django_otp.plugins.otp_static.admin import StaticDeviceAdmin
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.admin import TOTPDeviceAdmin
from django_otp.plugins.otp_totp.models import TOTPDevice

LABELS = {
    "user": (_("User"), _("The user this device belongs to.")),
    "name": (_("Name"), _("A readable name for this device.")),
    "confirmed": (_("Confirmed"), _("Is this device ready for use?")),
    "throttling_failure_timestamp": (
        _("Last failed attempt"), _("Time of the last failed verification; empty if the last attempt succeeded."),
    ),
    "throttling_failure_count": (_("Failed attempts in a row"), _("Number of successive failed attempts.")),
    "created_at": (_("Created at"), _("When this device was added.")),
    "last_used_at": (_("Last used at"), _("When this device was last used.")),
    "key": (_("Secret key"), _("Hex-encoded secret key, up to 40 bytes.")),
    "step": (_("Time step"), _("Length of one time step in seconds.")),
    "t0": (_("Start time"), _("Unix time at which step counting begins.")),
    "digits": (_("Digits"), _("Number of digits in a code.")),
    "tolerance": (_("Tolerance"), _("How many time steps before or after the current one are accepted.")),
    "drift": (_("Clock drift"), _("How many time steps the device's clock differs from ours.")),
    "last_t": (_("Last time step"), _("Time step of the last accepted code; the next code must be later.")),
}


class _PolishLabelsMixin:
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields = copy.deepcopy(form.base_fields)  # never touch shared Field objects
        for name, field in form.base_fields.items():
            if name in LABELS:
                field.label, field.help_text = LABELS[name]
        return form


for model, base in ((TOTPDevice, TOTPDeviceAdmin), (StaticDevice, StaticDeviceAdmin)):
    if admin.site.is_registered(model):
        admin.site.unregister(model)
    admin.site.register(model, type(base.__name__, (_PolishLabelsMixin, base), {}))
