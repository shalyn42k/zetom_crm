def filter_sidebar_items(request, items):
    filtered = []

    for item in items:
        perm = item.get("permission")

        # Если permission не указан — показываем всем
        if not perm:
            filtered.append(item)
            continue

        # Если permission это callable (lambda) — вызываем с request
        if callable(perm):
            if perm(request):
                filtered.append(item)
        # Иначе это строка (старый формат) — показываем элемент
        else:
            filtered.append(item)

    return filtered
