from django.urls import path

from .views import ClientSearchView, client_autofill, nip_lookup

app_name = "clients"

urlpatterns = [
    path("search/", ClientSearchView.as_view(), name="search"),
    path("autofill/", client_autofill, name="autofill"),
    # claude — company data from the VAT register by NIP
    path("nip-lookup/", nip_lookup, name="nip_lookup"),
]
