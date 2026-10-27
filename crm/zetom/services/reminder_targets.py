# claude
"""Who a work-log reminder may be addressed to ("Komu przypomnieć" in
step_notes_modal.html), shared by the modal's context and the create
endpoint so the form and the POST check can never disagree."""
from django.contrib.auth import get_user_model
from django.utils.translation import gettext

from crm.users.models import Role
from crm.users.utils import user_has_perm
from crm.zetom.models import StepNote

User = get_user_model()


def allowed_notify(user):
    """Notify values this user may pick, in display order."""
    allowed = [StepNote.Notify.SELF]
    if user_has_perm(user, "send_staff_messages"):
        allowed.append(StepNote.Notify.USERS)
        if user_has_perm(user, "message_roles"):
            allowed.append(StepNote.Notify.ROLES)
    if user_has_perm(user, "send_client_messages"):
        allowed.append(StepNote.Notify.CLIENT)
    return allowed


def _main_request(obj):
    return getattr(obj, "from_main", None) or obj


def client_email_choices(obj):
    """Distinct client addresses known for this request/document: its own
    email, the parent request's, then linked clients'. Nothing typed by hand."""
    if obj is None:
        return []
    emails = [getattr(obj, "email", "")]
    parent = getattr(obj, "from_main", None)
    if parent is not None:
        emails.append(parent.email)
    for holder in (obj, parent):
        if holder is not None and hasattr(holder, "clients"):
            emails.extend(holder.clients.exclude(email__isnull=True).values_list("email", flat=True))
    seen, result = set(), []
    for email in emails:
        email = (email or "").strip()
        if email and email.lower() not in seen:
            seen.add(email.lower())
            result.append(email)
    return result


def colleague_choices(user, obj):
    """Active staff except the author, people on this request first."""
    on_request = set(_main_request(obj).assigned_to.values_list("pk", flat=True)) if obj is not None else set()
    users = list(User.objects.filter(is_active=True, is_staff=True).exclude(pk=user.pk))
    users.sort(key=lambda u: (u.pk not in on_request, (u.get_full_name() or u.username).lower()))
    for u in users:
        u.on_request = u.pk in on_request
    return users


def role_choices():
    return [(r.code, str(r)) for r in Role.objects.order_by("name") if r.code != "all_seeing"]


def client_email_body(obj, code):
    """Ready-made email text for "Klientowi e-mailem"; separate sentences per
    document kind — Polish agreement differs for oferta / zlecenie / wniosek."""
    kind = type(obj).__name__
    if kind == "Oferta":
        text = gettext("Hello,\n\nwe would like to remind you about our offer %(code)s. "
                       "Please let us know if you have any questions or if we can proceed.")
    elif kind == "Zlecenie":
        text = gettext("Hello,\n\nwe would like to remind you about your order %(code)s. "
                       "Please contact us if anything needs to be clarified.")
    elif kind == "Wniosek":
        text = gettext("Hello,\n\nwe would like to remind you about your application %(code)s. "
                       "Please send us any missing documents or information.")
    else:
        text = gettext("Hello,\n\nwe would like to remind you about %(code)s.")
    return text % {"code": code}


def notify_context(user, obj, code):
    """Context for the "Komu przypomnieć" block of the work-log modal."""
    allowed = allowed_notify(user)
    return {
        "options": [(v, StepNote.Notify(v).label) for v in allowed],
        "colleagues": colleague_choices(user, obj) if StepNote.Notify.USERS in allowed else [],
        "roles": role_choices() if StepNote.Notify.ROLES in allowed else [],
        "client_emails": client_email_choices(obj) if StepNote.Notify.CLIENT in allowed else [],
        "client_body": client_email_body(obj, code) if StepNote.Notify.CLIENT in allowed else "",
    }


def thread_code(obj):
    """Short code shown to people: OFR-2026-0042, REQ-2026-0042, …"""
    from crm.notification.services.request_mail import document_code

    if type(obj).__name__ in ("Oferta", "Zlecenie", "Wniosek"):
        return document_code(obj)
    return f"REQ-{obj.created_at.year}-{obj.pk:04d}"
