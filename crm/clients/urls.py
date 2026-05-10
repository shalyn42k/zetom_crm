from django.urls import path
from .views import ClientSearchView, client_autofill

app_name = "clients"

urlpatterns = [
    path("search/", ClientSearchView.as_view(), name="search"),
    path("autofill/", client_autofill, name="autofill"),
]
