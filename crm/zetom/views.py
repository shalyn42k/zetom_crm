# Django imports
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext_lazy as _

# Notification app imports
from crm.notification.services.notification_service import (
    send_notification_to_staff,
)
from crm.users.utils import user_has_perm
# Zetom app imports
from crm.zetom.forms import AddRequestFormNull
from crm.zetom.models import RequestAttachment, RequestSource


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
# БАГ-8: теперь принимаем request.FILES и сохраняем каждый файл как RequestAttachment.
def email_template(request):
    if request.method == "POST":
        form = AddRequestFormNull(request.POST, request.FILES)
        if form.is_valid():
            new_request = form.save(commit=False)
            new_request.source = RequestSource.SITE
            new_request.save()
            for f in request.FILES.getlist("attachments"):
                RequestAttachment.objects.create(request_null=new_request, file=f)
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


# claude — authenticated file download for RequestAttachment. Replaces the
# raw /media/ links: those were public in DEBUG (anyone with the URL) and
# 404 in production (no media serving there).
@staff_member_required
def attachment_download(request, pk):
    from crm.zetom.services.visibility import visible_requests_for

    att = get_object_or_404(RequestAttachment, pk=pk)
    owner = att.owner()
    if owner is None or not user_has_perm(request.user, "view_requests"):
        raise Http404
    if not visible_requests_for(request.user, type(owner).all_objects.filter(pk=owner.pk)).exists():
        raise Http404
    try:
        handle = att.file.open("rb")
    except FileNotFoundError:
        raise Http404
    return FileResponse(handle, filename=att.display_name)
