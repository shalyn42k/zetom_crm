from django.urls import path

from crispy.views import crispy_form_view

app_name = "crispy"

urlpatterns = [
    path("form/", crispy_form_view, name="form"),
]
