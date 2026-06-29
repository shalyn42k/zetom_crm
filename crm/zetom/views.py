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


def _is_dns_error(error_message: str) -> bool:
    """Check if error message indicates a DNS/hostname resolution failure."""
    dns_indicators = [
        "name resolution",
        "getaddrinfo failed",
        "nodename nor servname provided",
        "No address associated with hostname",
        "Temporary failure in name resolution",
    ]
    error_lower = str(error_message).lower()
    return any(indicator.lower() in error_lower for indicator in dns_indicators)


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
                error_message = str(e)
                # Provide user-friendly error message based on error type
                if _is_dns_error(error_message):
                    user_message = _(
                        "Your request was created, but notification email could not be sent. "
                        "This is likely a server configuration issue (invalid SMTP host). "
                        "The staff will review your request manually."
                    )
                else:
                    user_message = _(
                        "Your request was created, but we encountered an issue sending the notification. "
                        "The staff will review your request manually."
                    )
                messages.error(request, user_message)
                return render(request, "zetom/email_template.html", {"form": form})
            return render(
                request,
                "zetom/email_template.html",
                {"submitted": True},
            )
    else:
        form = AddRequestFormNull()
    return render(request, "zetom/email_template.html", {"form": form})
