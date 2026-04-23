# Django imports
from django.http import HttpResponse
from django.shortcuts import render

# Notification app imports
from crm.notification.services.notification_service import \
    send_notification_to_staff
# Zetom app imports
from crm.zetom.forms import AddRequestFormNull


def email_template(request):
    message = None
    if request.method == "POST":
        form = AddRequestFormNull(request.POST)
        if form.is_valid():
            new_request = form.save()
            try:
                send_notification_to_staff(new_request)
                message = f"Все заебок со всем"
            except Exception as e:
                message = f"Все ок в базе, но с почтой нет"
        else:
            message = f"Все плохо: {form.errors}"
    else:
        form = AddRequestFormNull()
    return render(
        request,
        "zetom/email_template.html",
        {
            "message": message,
            "form": form,
        },
    )
