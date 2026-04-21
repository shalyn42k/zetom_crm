from permissions import ROLE_PERMISSIONS
from .models import RequestMain, Oferta
from statuses import Status, ArchiveState


def handle_child_change(child, new_status):  # изменение, создание , удаление ребёнка
    
    change_status(child, new_status)  # меняем статус ребёнка

    parent = child.from_main   # берем у родителя детей 
    if not parent:
        return

    update_parent(parent)


def change_status(child, new_status): # в скобках пишем название функции/класса откуда будем брать статусы   
    
    if new_status is None:
        return

    current_status = child.status

    # тут пишем проверку перехода статусов. например с new в in progress
    transitions = {
        Status.new: ["in_progress"],
        Status.in_progress: ["waiting"],
        Status.waiting: ["done"],
        Status.done: ["in_progress", "waiting"]
    }

    allowed = transitions.get(current_status, [])

    if new_status == current_status:
      return

    if new_status in allowed:
       child.status = new_status
       child.save()
    else:
       raise ValueError("Ошибка статуса")


def update_parent(parent):

    children = parent.oferta_set.all()
    highest_status = None


    if children.exists():

        priority = {
            Status.in_progress: 1,
            Status.waiting: 2,
            Status.new: 3,
            Status.done: 4
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



        # если есть хоть один не  done активный
    if not children.exists():
       parent.is_archived = True
    else:
       parent.is_archived = not children.exclude(status=Status.done).exists()

    parent.save()