from itertools import chain

from django.db import transaction

# from crm.users.permissions import ROLES_CONFIG
from crm.zetom.models import Oferta, RequestMain
from crm.zetom.services.statuses import ArchiveState, Status


def handle_child_change(child, new_status):
    with transaction.atomic():
        change_status(child, new_status)
        parent = child.from_main
        if parent:
            update_parent(parent)


def change_status(
    child, new_status
):  # в скобках пишем название функции/класса откуда будем брать статусы

    if new_status is None:
        return

    current_status = child.status

    # тут пишем проверку перехода статусов. например с new в in progress
    transitions = {
        Status.new: [Status.in_progress],
        Status.in_progress: [Status.waiting],
        Status.waiting: [Status.done],
        Status.done: [Status.waiting, Status.in_progress],
    }

    allowed = transitions.get(current_status, [])

    if new_status == current_status:
        return

    if new_status in allowed:
        child.status = new_status
        child.save()
    else:
        raise ValueError("Ошибка статуса")


# AI-edited (claude-opus-4-7, 2026-04-23): собирает детей из всех трёх обратных менеджеров через chain; заменил .exists()/.exclude() на Python-проверки. Написано Claude, пользователь не редактировал.
def update_parent(parent):

    children = list(
        chain(
            parent.oferta_set.all(),
            parent.zlecenie_set.all(),
            parent.wniosek_set.all(),
        )
    )
    highest_status = None

    if children:

        priority = {
            Status.in_progress: 1,
            Status.waiting: 2,
            Status.new: 3,
            Status.done: 4,
        }

        highest_priority = 5

        # проверка сильного статуса
        for child in children:
            if child.status in priority:
                if priority[child.status] < highest_priority:
                    highest_priority = priority[child.status]
                    highest_status = child.status

    if highest_status is not None:
        parent.status = highest_status


    # архивирование родителя

    # если есть хоть один не done активный
    if not children:
        parent.is_archived = True
    else:

        all_done= all(c.status == Status.done for c in children )

        if_all_done = (
            parent.oferta_set.exists() and
            parent.zlecenie_set.exists() and 
            parent.wniosek_set.exists()
        )
        parent.is_archived = all_done and if_all_done

        if highest_status == Status.done and if_all_done == False:
           parent.status = Status.in_progress

    parent.save()


# AI-suggested (claude-opus-4-7, 2026-04-23): вынос общего тела save_model из трёх админок, чтобы убрать копипаст. Дизайн/подсказка — Claude, код написал пользователь. Потенциальный запах: параметр messages_module тянет веб-слой в сервис — см. обсуждение 2026-04-23, рефактор отложен до появления второго вызывающего.
def save_child_with_status(request, obj, form, change, messages_module):
    new_status = form.cleaned_data.get("status")
    if change:
        obj.status = type(obj).objects.get(pk=obj.pk).status
    try:
        handle_child_change(obj, new_status)
    except ValueError as e:
        messages_module.error(request, str(e))
        return False
    return True
