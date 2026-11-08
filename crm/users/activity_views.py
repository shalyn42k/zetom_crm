from datetime import date

from django.contrib.admin import site
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET

from crm.users.services.activity_calendar import calendar_activity
from crm.users.utils import user_has_perm


@require_GET
def activity_calendar(request):
    if not user_has_perm(request.user, "view_requests"):
        raise PermissionDenied

    raw_month = request.GET.get("month")
    raw_year = request.GET.get("year")
    if raw_year is not None:
        raw_date = f"{raw_year}-{raw_month}-01"
    else:
        raw_date = f"{raw_month}-01" if raw_month is not None else request.GET.get("date")
    if raw_month is not None and not raw_month:
        return HttpResponseBadRequest(_("Invalid date."))
    if raw_date:
        try:
            selected = date.fromisoformat(raw_date)
        except ValueError:
            return HttpResponseBadRequest(_("Invalid date."))
        if raw_date != selected.isoformat() or not 1900 <= selected.year <= 9998:
            return HttpResponseBadRequest(_("Invalid date."))
    else:
        selected = timezone.localdate()

    context = {
        **site.each_context(request),
        "title": _("My activity calendar"),
        "month_options": [date(selected.year, month, 1) for month in range(1, 13)],
        **calendar_activity(request.user, selected, selected),
    }
    return render(request, "admin/activity_calendar.html", context)
