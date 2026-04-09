from django.shortcuts import render
from django.http import HttpResponse
from .forms import AddRequestFormNull
from django.forms import forms

def email_template(request):
    if request.method == 'POST':
        form = AddRequestFormNull(request.POST)
        if form.is_valid():
            form.save()
            return HttpResponse(f"Все ок")
        else:
            return HttpResponse(f"Все плохо: {form.errors}")
    return render(request, 'zetom/email_template.html')

