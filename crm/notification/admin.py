import json

from django.contrib import admin
from django.urls import NoReverseMatch, reverse
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from crm.notification.models import EmailNotification, Notification
from crm.notification.utils import render_notification
from crm.users.utils import user_has_perm


# claude — было json.dumps в <pre>: technically readable, but reads as raw
# code (braces, quotes) even for a two-key payload like
# {"request_id": 69, "stage": "new"} — flagged as "code in the interface"
# on the email-log detail page. Payloads here are flat dicts in practice
# (see callers of send_notification / EmailNotification.objects.create),
# so render those as a plain key/value list; anything with a nested
# dict/list (not expected, but the field is JSONField — no schema
# enforced) falls back to the old formatted-JSON <pre> rather than risk
# mangling a shape this wasn't designed for.
def _pretty_json(value):
    """Render a flat dict payload as key/value pairs; formatted JSON as fallback."""
    if not value:
        return "—"
    if isinstance(value, dict) and all(
        not isinstance(v, (dict, list)) for v in value.values()
    ):
        rows = format_html_join(
            "",
            "<div style='display:flex;gap:8px;padding:2px 0'>"
            "<span style='color:var(--font-subtle-light, #71717a);min-width:11ch'>{}</span>"
            "<span>{}</span></div>",
            ((k, "—" if v is None else v) for k, v in sorted(value.items())),
        )
        return format_html("<div>{}</div>", rows)
    text = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)
    return format_html("<pre style='white-space:pre-wrap;margin:0'>{}</pre>", text)


# claude — append-only лог. Удалять / редактировать запрещено даже супер-юзеру,
# чтобы аудит-история была настоящим immutable-логом (см. DOCS/rbac.md / README).
@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
    list_display = ("created_at", "kind", "recipient", "title_preview", "is_read")
    list_display_links = ("created_at", "title_preview")
    list_filter = ("kind", "is_read", "created_at")
    search_fields = ("recipient__username", "recipient__email", "template_name")
    # claude — Fix-round: the rendered text (the whole point — it's the
    # actual human-readable message) used to sit below template_name and
    # payload, both raw/technical, and target_content_type/target_object_id
    # were two separate raw fields (a content-type string + a bare number)
    # instead of one clickable link to the thing the notification is about.
    # Reordered so the readable message is the first thing you see, and
    # target_display replaces the split fields with a link.
    readonly_fields = (
        "recipient", "actor", "kind", "rendered_display",
        "target_display", "template_name", "payload_display",
        "is_read", "read_at", "created_at",
    )
    exclude = ("payload", "target_content_type", "target_object_id")
    ordering = ("-created_at",)

    # claude — append-only лог. view гейтится permission'ом, add/change/delete
    # запрещены всем (включая суперюзера), чтобы аудит был immutable.
    def has_view_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_notification_log")

    def has_module_permission(self, request):
        return user_has_perm(request.user, "view_notification_log")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    # claude — превью отрендеренного title в changelist'е, чтобы строки не выглядели как
    # "Notification object" / "template_name=..." и сразу было видно о чём оно.
    @admin.display(description=_("Title"))
    def title_preview(self, obj):
        title, _ = render_notification(obj)
        return title or "—"

    # claude — полный отрендеренный текст (title + body) в детальной странице.
    @admin.display(description=_("Rendered"))
    def rendered_display(self, obj):
        title, body = render_notification(obj)
        if not title and not body:
            return "—"
        text = title
        if body:
            text = f"{title}\n\n{body}"
        return format_html("<pre style='white-space:pre-wrap;margin:0'>{}</pre>", text)

    @admin.display(description=_("Payload"))
    def payload_display(self, obj):
        return _pretty_json(obj.payload)

    # claude — Fix-round: replaces the raw target_content_type +
    # target_object_id pair (e.g. "Zetom CRM | Informacje" next to a bare
    # "72") with one link, labelled with the target's own __str__ (its
    # company name for a RequestMain), that jumps straight to that object's
    # admin page. Falls back gracefully if the target was hard-deleted
    # (target_content_type set NULL by the FK) or soft-removed since (the
    # GenericForeignKey then resolves to None) — still names the type and
    # id so the notification stays traceable even though there's nothing
    # left to link to.
    @admin.display(description=_("About"))
    def target_display(self, obj):
        if obj.target_content_type_id is None or obj.target_object_id is None:
            return "—"
        ct_label = str(obj.target_content_type)
        target = obj.target
        if target is None:
            return format_html(
                "{} — #{} ({})",
                ct_label, obj.target_object_id, _("no longer exists"),
            )
        opts = obj.target_content_type.model_class()._meta
        try:
            url = reverse(
                f"admin:{opts.app_label}_{opts.model_name}_change",
                args=[obj.target_object_id],
            )
        except NoReverseMatch:
            return format_html("{} — #{}", ct_label, obj.target_object_id)
        return format_html(
            '<a href="{}">{}</a> <span style="color:var(--font-subtle-light, #71717a)">({})</span>',
            url, str(target), ct_label,
        )


# claude
@admin.register(EmailNotification)
class EmailNotificationAdmin(ModelAdmin):
    list_display = ("created_at", "status", "subject", "recipient_email", "sent_at")
    list_display_links = ("created_at", "subject")
    list_filter = ("status", "created_at")
    search_fields = ("recipient_email", "subject", "template_name")
    readonly_fields = (
        "recipient_email", "actor", "template_name", "subject", "payload_display",
        "status", "status_reason", "sent_at", "created_at",
    )
    exclude = ("payload",)
    ordering = ("-created_at",)

    # claude — то же что для NotificationAdmin, только другой permission-код.
    def has_view_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_email_log")

    def has_module_permission(self, request):
        return user_has_perm(request.user, "view_email_log")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description=_("Payload"))
    def payload_display(self, obj):
        return _pretty_json(obj.payload)
