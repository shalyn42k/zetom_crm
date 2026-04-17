from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from crispy.forms import CrispyDemoForm


@staff_member_required
def crispy_form_view(request):
    form = CrispyDemoForm(request.POST or None, request.FILES or None)

    if request.method == "POST":
        button_name = request.POST.get("action", "submit")
        button_messages = {
            "submit": _("Submit button was clicked."),
            "submit_2": _("Submit 2 button was clicked."),
            "submit_3": _("Submit 3 button was clicked."),
        }

        if form.is_valid():
            messages.success(request, button_messages.get(button_name, _("Button was clicked.")))
        else:
            messages.error(request, _("Form contains validation errors."))

    context = {
        "title": _("Crispy form"),
        "form": form,
    }
    return render(request, "crispy/form.html", context)
