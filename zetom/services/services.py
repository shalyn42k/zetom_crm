from zetom.statuses import Status


def handle_child_change(child, new_status):
    """
    Обработка изменения дочернего объекта:
    - меняем статус ребёнка
    - обновляем родителя
    """

    change_status(child, new_status)

    parent = child.from_main
    if not parent:
        return

    update_parent(parent)


def change_status(child, new_status):
    """
    Меняет статус с проверкой переходов
    """

    if not new_status or new_status == child.status:
        return

    transitions = {
        Status.new: ["in_progress"],
        Status.in_progress: ["waiting"],
        Status.waiting: ["done"],
        Status.done: ["in_progress", "waiting"],
    }

    allowed = transitions.get(child.status, [])

    if new_status not in allowed:
        raise ValueError("Ошибка статуса: недопустимый переход")

    child.status = new_status
    child.save()


def update_parent(parent: RequestMain):
    """
    Обновляет статус и архив родителя на основе детей
    """

    children = parent.ofertas.all()

    # если нет детей — просто сбрасываем архив
    if not children.exists():
        parent.is_archived = False
        parent.save()
        return

    priority = {
        Status.in_progress: 1,
        Status.waiting: 2,
        Status.new: 3,
        Status.done: 4,
    }

    highest_status = None
    best_priority = 999

    for child in children:
        if child.status in priority:
            if priority[child.status] < best_priority:
                best_priority = priority[child.status]
                highest_status = child.status

    # обновляем статус родителя
    if highest_status and parent.status != highest_status:
        parent.status = highest_status

    # архив:
    # архивируем ТОЛЬКО если ВСЕ дети done
    parent.is_archived = not children.exclude(status=Status.done).exists()

    parent.save()