# Django imports
from django.contrib import messages
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

# Notification app imports
from crm.notification.services.notification_service import (
    send_notification_to_staff,
)
# Zetom app imports
from crm.zetom.forms import AddRequestFormNull
from crm.zetom.models import RequestSource


# claude — раньше после успешного POST редиректило в
# admin:zetom_requestnull_change, что для анонимного юзера с сайта = редирект
# в /admin/login/?next=... Теперь рендерим ту же страницу в thank-you state.
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
                messages.error(request, _("Notification failed: %(err)s") % {"err": e})
                return render(request, "zetom/email_template.html", {"form": form})
            return render(
                request,
                "zetom/email_template.html",
                {"submitted": True},
            )
    else:
        form = AddRequestFormNull()
    return render(request, "zetom/email_template.html", {"form": form})
