# Django imports
from django.urls import path

from . import views

app_name = "zetom"

urlpatterns = [
    path("email/", views.email_template, name="index"),
    # claude — authenticated download of request/document files.
    path("attachments/<int:pk>/", views.attachment_download, name="attachment"),
]
