# claude
"""In-app notification for restoring a request from the trash.

RequestMain restores already emit a STATUS_CHANGE in-app notification through
`notification.signals` (the deleted→active status flip fires the post_save
receiver). RequestNull leads have no status field and no wired signal, so their
restore needs an explicit notification — that's what this module provides.

Recipients follow the usual cascade (`default_recipients`): owners →
dep_heads-of-departments → admins. A Validation Window lead has no owners, so it
resolves to the dep_heads of its departments, or admins as the final fallback.
"""
from crm.notification.models import NotificationKind
from crm.notification.services import inapp_service
from crm.notification.services.recipients import default_recipients

REQUEST_RESTORED_TEMPLATE = "notification/inapp/staff/request_restored.txt"


def notify_validation_request_restored(rn, *, actor=None):
    """Tell the responsible staff that a Validation Window lead was restored."""
    recipients = default_recipients(rn)
    inapp_service.create_inapp(
        kind=NotificationKind.SYSTEM,
        template_name=REQUEST_RESTORED_TEMPLATE,
        payload={
            "request_id": rn.pk,
            "request_label": f"NULL-{rn.pk} — {rn.company_name or '—'}",
            "source": rn.source,
            "actor_name": (
                actor.get_full_name() or actor.username if actor else "system"
            ),
        },
        recipients=recipients,
        actor=actor,
        target=rn,
    )
