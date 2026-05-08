# Django imports
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render

# Notification app imports
from crm.notification.services.notification_service import \
    send_notification_to_staff
# Zetom app imports
from crm.zetom.forms import AddRequestFormNull
from crm.zetom.models import RequestSource


def email_template(request):
    if request.method == "POST":
        form = AddRequestFormNull(request.POST)
        if form.is_valid():
            new_request = form.save(commit=False)
            new_request.source = RequestSource.SITE
            new_request.save()
            try:
                send_notification_to_staff(new_request)
            except Exception as e:
                messages.error(request, f"Notification failed: {e}")
                return render(request, "zetom/email_template.html", {"form": form})
            return redirect("admin:zetom_requestnull_change", new_request.pk)
    else:
        form = AddRequestFormNull()
    return render(request, "zetom/email_template.html", {"form": form})
