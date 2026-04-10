from django.shortcuts import render
from django.http import HttpResponse
from django.forms import forms

from .forms import AddRequestFormNull
from .emails.email_utils import send_notification_to_staff

def email_template(request):
    if request.method == 'POST':
        form = AddRequestFormNull(request.POST)
        if form.is_valid():
            new_request = form.save()
            try:
                send_notification_to_staff(new_request)
                message = ("Все заебок со всем")
            except Exception as e:
                message = "Все ок в базе, но с почтой нет"
                    # тут написать че случится если имейл не удалось отправить
        else:
            return HttpResponse(f"Все плохо: {form.errors}")
    return render(request, 'zetom/email_template.html', {
        'message': message
    })

