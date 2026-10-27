# claude
"""What a message can be attached to, and who it may be sent to from there.

Shared by the compose/cancel views and by the composer panel's context
builder on the document window, so the form and the POST handler agree on
which targets, client addresses and roles are allowed.
"""
from django.contrib.auth import get_user_model
from django.utils.translation import gettext, gettext_lazy as _

from crm.notification.models import MessageAudience, ScheduledMessage
from crm.users.models import Role
from crm.users.utils import user_has_perm

User = get_user_model()

# key used in the form's hidden "target" field -> model name in crm.zetom
TARGET_MODELS = ("requestmain", "oferta", "zlecenie", "wniosek")


def target_key(obj):
    return f"{type(obj).__name__.lower()}:{obj.pk}"


def resolve_target(user, key):
    """Turn "oferta:12" into the Oferta, or None if unknown or not visible."""
    from django.apps import apps

    from crm.zetom.services.visibility import visible_requests_for

    model_name, _sep, pk = (key or "").partition(":")
    if model_name not in TARGET_MODELS or not pk.isdigit():
        return None
    model = apps.get_model("zetom", model_name)
    return visible_requests_for(user, model.objects.all()).filter(pk=int(pk)).first()


def client_email_choices(target):
    """Distinct client addresses known for this document/request, in order:
    the document's own email, the parent request's, then linked clients'."""
    if target is None:
        return []
    emails = [getattr(target, "email", "")]
    parent = getattr(target, "from_main", None)
    if parent is not None:
        emails.append(parent.email)
    if hasattr(target, "clients"):
        emails.extend(target.clients.exclude(email__isnull=True).values_list("email", flat=True))
    seen, result = set(), []
    for email in emails:
        email = (email or "").strip()
        if email and email.lower() not in seen:
            seen.add(email.lower())
            result.append(email)
    return result


def allowed_audiences(user):
    allowed = []
    if user_has_perm(user, "send_client_messages"):
        allowed.append(MessageAudience.CLIENT)
    if user_has_perm(user, "send_staff_messages"):
        allowed.append(MessageAudience.USERS)
        if user_has_perm(user, "message_roles"):
            allowed.append(MessageAudience.ROLES)
    return allowed


def staff_user_choices(user):
    return (
        User.objects.filter(is_active=True, is_staff=True)
        .exclude(pk=user.pk)
        .order_by("first_name", "last_name", "username")
    )


def role_choices():
    return [(r.code, str(r)) for r in Role.objects.order_by("name") if r.code != "all_seeing"]


def can_cancel(user, message):
    return message.author_id == user.pk or user.is_superuser or user_has_perm(user, "manage_notification_settings")


def messages_for_target(target):
    from django.contrib.contenttypes.models import ContentType

    if target is None:
        return ScheduledMessage.objects.none()
    ct = ContentType.objects.get_for_model(type(target))
    return (
        ScheduledMessage.objects.filter(target_content_type=ct, target_object_id=target.pk)
        .select_related("author")
        .prefetch_related("recipient_users")
        .order_by("-send_at")
    )


AUDIENCE_HINTS = {
    MessageAudience.CLIENT: _("Email to the client's address on this document."),
    MessageAudience.USERS: _("Chosen colleagues get it in their inbox and/or by email."),
    MessageAudience.ROLES: _("Everyone with the selected roles gets it."),
}


def _presets(target, code):
    """Ready-made subject/body pairs the composer can drop in. Kind-specific
    sentences, one catalog entry each — Polish needs a different gender
    agreement for oferta (f.) / zlecenie (n.) / wniosek (m.)."""
    kind = type(target).__name__
    client_body = {
        "Oferta": gettext("Hello,\n\nwe would like to remind you about our offer %(code)s. "
                     "Please let us know if you have any questions or if we can proceed."),
        "Zlecenie": gettext("Hello,\n\nwe would like to remind you about your order %(code)s. "
                       "Please contact us if anything needs to be clarified."),
        "Wniosek": gettext("Hello,\n\nwe would like to remind you about your application %(code)s. "
                      "Please send us any missing documents or information."),
    }.get(kind, gettext("Hello,\n\nwe would like to remind you about %(code)s."))
    return [
        {
            "key": "client_reminder",
            "label": gettext("Reminder to the client"),
            "audience": MessageAudience.CLIENT,
            "subject": gettext("Reminder: %(code)s") % {"code": code},
            "body": client_body % {"code": code},
        },
        {
            "key": "staff_reminder",
            "label": gettext("Reminder to colleagues"),
            "audience": MessageAudience.USERS,
            "subject": gettext("Please follow up: %(code)s") % {"code": code},
            "body": gettext("Please take a look at %(code)s and follow up with the client.") % {"code": code},
        },
    ]


def build_composer_context(request, target, code):
    """Everything notification/_composer.html needs for one document."""
    from crm.notification.forms import MessageComposeForm

    user = request.user
    audiences = allowed_audiences(user)
    form = MessageComposeForm(user=user, target=target)
    items = list(messages_for_target(target)[:20])
    for m in items:
        m.can_cancel = m.status == "PENDING" and can_cancel(user, m)
    return {
        "enabled": bool(audiences),
        "form": form,
        "target_key": target_key(target),
        "audiences": [(a, MessageAudience(a).label, AUDIENCE_HINTS[a]) for a in audiences],
        "client_emails": client_email_choices(target),
        "presets": [p for p in _presets(target, code) if p["audience"] in audiences],
        "messages": items,
    }
