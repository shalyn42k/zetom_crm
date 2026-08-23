# claude
# claude
from django.core.exceptions import ValidationError
from django.urls import reverse

from crm.clients.models import Client, Company, CompanyPersonLink
from crm.clients.validators import normalize_nip, validate_nip
from crm.status_manager.services.statuses import RequestStatus
from crm.zetom.models import DepartmentsVariants

# claude — avatar background palette (CSS class suffix). Stable per user so the
# same person keeps the same colour across requests/tabs.
_AVATAR_COLORS = ("c-blue", "c-purple", "c-green", "c-slate")

# claude — id prefix + admin change-view name per request type tab.
_TYPE_META = {
    "main": {"prefix": "", "change": "admin:zetom_requestmain_change"},
    "oferta": {"prefix": "OF-", "change": "admin:zetom_oferta_change"},
    "zlecenie": {"prefix": "ZL-", "change": "admin:zetom_zlecenie_change"},
    "wniosek": {"prefix": "WN-", "change": "admin:zetom_wniosek_change"},
}


# claude
def _user_avatar(user) -> dict:
    """Initials + a stable colour class for an owner avatar."""
    first = (user.first_name or "")[:1].upper()
    last = (user.last_name or "")[:1].upper()
    initials = (first + last) or (user.username[:2].upper() if user.username else "?")
    color = _AVATAR_COLORS[user.pk % len(_AVATAR_COLORS)]
    return {"initials": initials, "color": color}


# claude
def _dept_label(codes) -> str:
    """First department label of a request (ArrayField of codes)."""
    if not codes:
        return ""
    labels = dict(DepartmentsVariants.choices)
    return str(labels.get(codes[0], codes[0]))


# claude
def build_request_rows(requests, request_type: str, owners_attr: str = "assigned_to") -> list[dict]:
    """Shape a queryset of one request type into template-ready rows.

    `request_type` is one of main/oferta/zlecenie/wniosek (drives the id prefix
    and the open-link). `owners_attr` is the M2M holding the people to show as
    the owner avatar stack (owners for RequestMain, assigned_to otherwise).
    """
    meta = _TYPE_META[request_type]
    rows = []
    for obj in requests:
        people = list(getattr(obj, owners_attr).all())
        avatars = [_user_avatar(u) for u in people[:3]]
        extra = len(people) - 3
        rows.append({
            "pk": obj.pk,
            "label": f"{meta['prefix']}{obj.pk}",
            "date": obj.created_at,
            "status": obj.status,
            "dept": _dept_label(obj.departments),
            "avatars": avatars,
            "extra_owners": extra if extra > 0 else 0,
            "change_url": reverse(meta["change"], args=[obj.pk]),
        })
    return rows


# claude
def get_client_request_summary(client: Client) -> dict:
    """Return counts of linked documents for a given Client."""
    request_main_count = (
        client.requests
        .exclude(status__in=[RequestStatus.cancelled, RequestStatus.deleted])
        .count()
    )
    oferta_count = client.ofertas.count()
    zlecenie_count = client.zlecenia.count()
    wniosek_count = client.wnioski.count()

    return {
        "request_main": request_main_count,
        "oferta": oferta_count,
        "zlecenie": zlecenie_count,
        "wniosek": wniosek_count,
    }


# claude — единая точка создания «человек + (опц.) фирма» для интейка.
# Дедуп фирмы повторяет логику backfill: по NIP, иначе по имени.
def create_person_with_company(
    *, first_name="", last_name="", phone=None, email="",
    company_name="", company_nip=None, address="", linked_by=None,
):
    client = Client.objects.create(
        first_name=first_name or None,
        last_name=last_name or None,
        phone=phone or None,
        email=email or None,
    )

    # claude — the checksum is verified here, not just the shape. Company is the
    # reference book everything else dedupes and searches against, so a NIP with
    # a typo must not enter it: it would create a firm no later lookup can ever
    # match, and the card refuses to re-save it (views._clean_nip).
    #
    # Nothing is lost by dropping it — company_nip is a field on the request
    # itself, so the value the operator typed stays visible there. Here it just
    # means "dedupe this firm by name instead".
    nip = None
    if company_nip:
        try:
            nip = normalize_nip(company_nip)
            validate_nip(nip)
        except ValidationError:
            nip = None

    company = None
    if nip:
        company, _created = Company.objects.get_or_create(
            nip=nip,
            defaults={"name": company_name or nip, "comments": address or ""},
        )
    elif company_name:
        stripped = company_name.strip()
        company = Company.objects.filter(name__iexact=stripped).order_by("id").first()
        if company is None:
            company = Company.objects.create(name=stripped, comments=address or "")

    if company is not None:
        CompanyPersonLink.objects.get_or_create(
            company=company, person=client, defaults={"linked_by": linked_by},
        )
    return client, company
