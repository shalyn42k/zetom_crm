import calendar
from collections import defaultdict
from datetime import timedelta

from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from crm.notification.services.followup_reminders import resolve_followup_recipients
from crm.status_manager.models import ChildDocumentDeletion, StatusHistory
from crm.status_manager.services.statuses import RequestStatus
from crm.zetom.models import Oferta, RequestMain, StepNote, Wniosek, Zlecenie
from crm.zetom.services.step_notes import OPEN_REMINDER_FILTER
from crm.zetom.services.visibility import visible_requests_for


def calendar_activity(user, month, selected):
    """Build a monthly calendar from recorded events attributable to this user."""
    first = month.replace(day=1)
    last = month.replace(day=calendar.monthrange(month.year, month.month)[1])
    visible = visible_requests_for(user, RequestMain.objects.all()).exclude(
        status=RequestStatus.deleted
    )
    visible_ids = visible.values("pk")
    events = defaultdict(lambda: defaultdict(list))

    def add(request_id, timestamp, label, details=""):
        day = timezone.localtime(timestamp).date()
        if first <= day <= last:
            events[day][request_id].append(
                {"time": timestamp, "label": label, "details": details}
            )

    for history in RequestMain.history.filter(
        id__in=visible_ids, history_user=user,
        history_date__date__range=(first, last),
    ).order_by("history_date"):
        labels = {"+": _("Request created"), "~": _("Request updated"), "-": _("Request deleted")}
        details = ""
        if history.history_type == "~" and timezone.localtime(history.history_date).date() == selected:
            previous = history.prev_record
            if previous:
                details = "\n".join(
                    f"{RequestMain._meta.get_field(change.field).verbose_name}: "
                    f"{change.old if change.old is not None else '—'} → "
                    f"{change.new if change.new is not None else '—'}"
                    for change in history.diff_against(previous).changes
                )
        add(history.id, history.history_date, labels[history.history_type], details)

    for entry in StatusHistory.objects.filter(
        request_id__in=visible_ids, changed_by=user,
        changed_at__date__range=(first, last),
    ):
        details = f"{entry.get_old_status_display()} → {entry.get_new_status_display()}"
        if entry.reason:
            details += f" · {_(entry.reason)}"
        add(entry.request_id, entry.changed_at, _("Status changed"), details)

    models = (RequestMain, Oferta, Zlecenie, Wniosek)
    types = ContentType.objects.get_for_models(*models)
    notes = list(StepNote.objects.filter(
        author=user, created_at__date__range=(first, last),
        target_content_type_id__in=[types[model].pk for model in models],
    ).select_related("target_content_type"))
    planned_notes = list(
        StepNote.objects.filter(
            OPEN_REMINDER_FILTER,
            next_contact_at__date__range=(first, last),
            target_content_type_id__in=[types[model].pk for model in models],
        ).select_related("author", "target_content_type")
    )
    logs = list(LogEntry.objects.filter(
        user=user, content_type_id__in=[types[model].pk for model in models],
        action_time__date__range=(first, last),
    ).select_related("content_type"))
    target_map = {}
    targets = {}
    for model in models:
        ct_id = types[model].pk
        ids = {
            note.target_object_id for note in notes + planned_notes
            if note.target_content_type_id == ct_id
        }
        ids.update(
            int(entry.object_id) for entry in logs
            if entry.content_type_id == ct_id and entry.object_id and entry.object_id.isdecimal()
        )
        if model is RequestMain:
            objects = visible.filter(pk__in=ids)
        else:
            objects = visible_requests_for(
                user, model.objects.filter(pk__in=ids, from_main_id__in=visible_ids)
            ).select_related("from_main")
        for obj in objects:
            key = (ct_id, obj.pk)
            targets[key] = obj
            target_map[key] = obj.pk if model is RequestMain else obj.from_main_id

    reminders = defaultdict(list)
    for note in planned_notes:
        key = (note.target_content_type_id, note.target_object_id)
        target = targets.get(key)
        if target is None:
            continue
        if note.notify == StepNote.Notify.CLIENT:
            if note.author_id != user.pk:
                continue
        elif not any(recipient.pk == user.pk for recipient in resolve_followup_recipients(note, target)):
            continue
        day = timezone.localtime(note.next_contact_at).date()
        reminders[day].append({"note": note, "request_id": target_map[key]})

    for note in notes:
        parent_id = target_map.get((note.target_content_type_id, note.target_object_id))
        if parent_id is not None:
            label = _("Reminder created") if note.kind == StepNote.Kind.REMINDER else _("Contact recorded")
            details = " · ".join(filter(None, (
                str(note.target_content_type.name),
                note.get_channel_display() if note.channel else "",
                note.action,
                note.text,
            )))
            if note.next_contact_at:
                details += (" · " if details else "") + str(
                    timezone.localtime(note.next_contact_at).strftime("%d.%m.%Y %H:%M")
                )
            add(parent_id, note.created_at, label, details)

    for entry in logs:
        if not entry.object_id or not entry.object_id.isdecimal():
            continue
        parent_id = target_map.get((entry.content_type_id, int(entry.object_id)))
        if parent_id is not None:
            details = " · ".join(filter(None, (
                str(entry.content_type.name), entry.object_repr, entry.get_change_message()
            )))
            label = _("Request administration") if entry.content_type_id == types[RequestMain].pk else _("Document activity")
            add(parent_id, entry.action_time, label, details)

    for entry in ChildDocumentDeletion.objects.filter(
        from_main_id__in=visible_ids, deleted_by=user,
        deleted_at__date__range=(first, last),
    ):
        add(entry.from_main_id, entry.deleted_at, _("Document deleted"),
            " · ".join(filter(None, (entry.document_repr, entry.reason))))

    weeks = []
    today = timezone.localdate()
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(first.year, first.month):
        weeks.append([
            {
                "date": day,
                "in_month": day.month == first.month,
                "count": len(events.get(day, {})),
                "reminder_count": len(reminders.get(day, [])),
                "selected": day == selected,
                "today": day == today,
            }
            for day in week
        ])

    rows = []
    selected_events = events.get(selected, {})
    selected_reminders = reminders.get(selected, [])
    request_ids = set(selected_events) | {item["request_id"] for item in selected_reminders}
    requests = {obj.pk: obj for obj in visible.filter(pk__in=request_ids)}

    def request_url(obj):
        name = "admin:zetom_cancelledrequest_change" if obj.status == RequestStatus.cancelled else "admin:zetom_requestmain_change"
        return reverse(name, args=[obj.pk])

    for request_id, request_events in selected_events.items():
        obj = requests.get(request_id)
        if obj is None:
            continue
        rows.append({
            "request": obj,
            "url": request_url(obj),
            "events": sorted(request_events, key=lambda event: event["time"], reverse=True),
        })
    rows.sort(key=lambda row: row["events"][0]["time"], reverse=True)
    reminder_rows = []
    for item in sorted(selected_reminders, key=lambda item: item["note"].next_contact_at):
        obj = requests.get(item["request_id"])
        if obj is not None:
            reminder_rows.append({
                "request": obj,
                "url": request_url(obj),
                "note": item["note"],
            })

    return {
        "month": first,
        "selected": selected,
        "weeks": weeks,
        "rows": rows,
        "reminders": reminder_rows,
        "day_count": len(rows),
        "month_count": len({pk for day in events.values() for pk in day}),
        "event_count": sum(len(items) for day in events.values() for items in day.values()),
        "previous": (first - timedelta(days=1)).replace(day=1) if first.year > 1900 or first.month > 1 else None,
        "next": (last + timedelta(days=1)) if last.year < 9998 or last.month < 12 else None,
    }
