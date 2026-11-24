from django.core.exceptions import FieldDoesNotExist

from crm.status_manager.services.statuses import RequestStatus
from crm.zetom.models import RequestMain, RequestSource, department_choices


def history_field_label(field_name):
    try:
        return str(RequestMain._meta.get_field(field_name).verbose_name)
    except FieldDoesNotExist:
        return field_name


def history_value_label(field_name, value):
    if value in (None, ""):
        return value
    choices = {"status": RequestStatus.choices, "source": RequestSource.choices}
    if field_name in choices:
        return str(dict(choices[field_name]).get(value, value))
    if field_name == "departments" and isinstance(value, (list, tuple)):
        labels = dict(department_choices())
        return ", ".join(str(labels.get(code, code)) for code in value)
    return value
