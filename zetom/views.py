from django.shortcuts import render
from django.http import HttpResponse

from .forms import AddRequestFormNull
from .emails.email_utils import send_notification_to_staff

def email_template(request):
    message = None
    if request.method == "POST":
        form = AddRequestFormNull(request.POST)
        if form.is_valid():
            new_request = form.save()
            try:
                send_notification_to_staff(new_request)
                message = "Все заебок со всем"
            except Exception as e:
                message = "Все ок в базе, но с почтой нет"
        else:
            return HttpResponse(f"Все плохо: {form.errors}")
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
        
