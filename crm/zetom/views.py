import hmac
import json
import logging
from datetime import timedelta

# Django imports
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

# Notification app imports
from crm.notification.services.notification_service import (
    send_notification_to_staff,
)
from crm.users.utils import user_has_perm
# Zetom app imports
from crm.zetom.forms import AddRequestFormNull
from crm.zetom.models import RequestAttachment, RequestNull, RequestSource
from crm.zetom.services.throttle import public_form_allowed
from crm.zetom.services.uploads import upload_errors

logger = logging.getLogger(__name__)


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
        # claude — anonymous endpoint: cap submissions per IP and the files
        # (count + size) before anything is written.
        if not public_form_allowed(request):
            form = AddRequestFormNull(request.POST)
            form.full_clean()
            form.add_error(None, _("Too many requests from your address. Please try again later."))
            return render(request, "zetom/email_template.html", {"form": form}, status=429)
        form = AddRequestFormNull(request.POST, request.FILES)
        for error in upload_errors(
            request.FILES.getlist("attachments"), max_files=settings.PUBLIC_FORM_MAX_FILES,
        ):
            form.add_error(None, error)
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
    response = FileResponse(handle, filename=att.display_name)
    # claude — files come from anonymous visitors (public form) too, and are
    # shown inline (saved document sheets are .html). An uploaded .html/.svg
    # would otherwise run its scripts on the CRM origin with the viewer's
    # session. The CSP sandbox opens it in an isolated origin with scripts
    # off; nosniff stops the browser second-guessing the content type.
    # Not for PDF: Chrome refuses to start its PDF viewer in a sandbox, and
    # that viewer doesn't give the file access to the CRM origin anyway.
    if response.get("Content-Type", "").split(";")[0] != "application/pdf":
        response["Content-Security-Policy"] = "sandbox"
    response["X-Content-Type-Options"] = "nosniff"
    return response


# claude — intake for the client's WordPress site (zetomkatowice.eu): its
# Divi contact form forwards every submission here as JSON, authenticated by
# a shared token (SITE_INTAKE_TOKEN). The site keeps sending its own e-mail,
# so a rejected or failed call never loses a lead. Only the contact fields
# are taken from the payload (never `client`, `status`, ...).
SITE_INTAKE_FIELDS = ("first_name", "last_name", "phone", "email", "company_name", "message")
# A double click or a retry from the site within this window returns the
# request already created instead of a second one.
SITE_INTAKE_DEDUP_WINDOW = timedelta(minutes=10)


def _site_token_ok(request, expected):
    header = request.headers.get("Authorization", "")
    scheme, _sep, token = header.partition(" ")
    return scheme == "Bearer" and hmac.compare_digest(token.strip(), expected)


@csrf_exempt
@require_POST
def site_request(request):
    expected = getattr(settings, "SITE_INTAKE_TOKEN", "")
    if not expected:
        raise Http404
    if not _site_token_ok(request, expected):
        return JsonResponse({"error": "unauthorized"}, status=401)
    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "invalid json"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "invalid json"}, status=400)

    data = {name: str(payload.get(name) or "").strip() for name in SITE_INTAKE_FIELDS}
    form = AddRequestFormNull(data)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

    duplicate = RequestNull.objects.filter(
        source=RequestSource.SITE,
        email=form.cleaned_data["email"],
        message=form.cleaned_data["message"],
        created_at__gte=timezone.now() - SITE_INTAKE_DEDUP_WINDOW,
    ).order_by("-created_at").first()
    if duplicate is not None:
        return JsonResponse({"id": duplicate.pk, "duplicate": True}, status=200)

    new_request = form.save(commit=False)
    new_request.source = RequestSource.SITE
    new_request.save()
    try:
        send_notification_to_staff(new_request)
    except Exception:
        logger.exception("site_request: staff notification failed for RequestNull %s", new_request.pk)
    return JsonResponse({"id": new_request.pk}, status=201)
