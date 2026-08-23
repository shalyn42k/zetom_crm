"""
URL configuration for zetom_crm project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from crm.clients.views import company_changelist_redirect

urlpatterns = [
    # claude — the stock Company changelist, replaced by the Klienci list.
    # Same reasoning as the app index below; see the view for details. Must sit
    # BEFORE admin.site.urls to win the match.
    path("admin/clients/company/", company_changelist_redirect),
    # claude — /admin/clients/ is Django's app index: a bare page listing the
    # three registered models (Client, Company, Client interaction). Unfold
    # links it from the breadcrumbs on every clients screen, so going "back"
    # from a card landed users on a three-way choice instead of the list they
    # meant. Sent to the unified Klienci list instead. Must sit BEFORE
    # admin.site.urls to win the match; the app index has no other entry point.
    path(
        "admin/clients/",
        RedirectView.as_view(
            pattern_name="admin:clients_client_changelist", permanent=False,
        ),
    ),
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("zetom/", include("crm.zetom.urls")),
    path("users/", include("crm.users.urls")),
    path("clients/", include("crm.clients.urls")),
    path("notifications/", include("crm.notification.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
