# claude
"""Бэкфилл нормализованных Company/связей из легаси текст-полей Client.
Функция принимает классы моделей аргументами: тот же код вызывается из
data-миграции (через apps.get_model) и из теста (реальные модели)."""
from django.core.exceptions import ValidationError

from crm.clients.validators import normalize_nip


def _dedup_key(client):
    """Ключ дедупа фирмы: нормализованный NIP если валиден, иначе имя."""
    if client.company_nip:
        try:
            return ("nip", normalize_nip(client.company_nip))
        except ValidationError:
            pass
    if client.company_name:
        return ("name", client.company_name.strip().lower())
    return None


def backfill_companies(Client, Company, CompanyPersonLink, RequestMain, RequestClientLink):
    # 1. Company + связи из Client.company_*
    cache = {}  # dedup_key -> Company
    for client in Client.objects.all():
        key = _dedup_key(client)
        if key is None:
            continue
        company = cache.get(key)
        if company is None:
            kind, value = key
            if kind == "nip":
                company, _created = Company.objects.get_or_create(
                    nip=value,
                    defaults={"name": client.company_name or value, "comments": client.address or ""},
                )
            else:  # dedup by name — case-insensitive, tolerant of pre-existing duplicate names
                stripped = client.company_name.strip()
                company = Company.objects.filter(name__iexact=stripped).order_by("id").first()
                if company is None:
                    company = Company.objects.create(name=stripped, comments=client.address or "")
            cache[key] = company
        CompanyPersonLink.objects.get_or_create(company=company, person=client)

    # 2. RequestMain.company из связей (если однозначно)
    for link in RequestClientLink.objects.select_related("request", "client"):
        req = link.request
        if req.company_id is not None:
            continue
        companies = list(
            CompanyPersonLink.objects.filter(person=link.client)
            .values_list("company_id", flat=True)
        )
        if len(set(companies)) == 1:
            req.company_id = companies[0]
            req.save(update_fields=["company"])
