from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext
from django.views import View
from django.views.decorators.http import require_POST
from phonenumber_field.phonenumber import to_python as phone_to_python

from crm.clients.models import Client, Company, CompanyPersonLink, SupplierType
from crm.clients.validators import normalize_nip, validate_nip
from crm.status_manager.services.statuses import RequestStatus
from crm.users.utils import user_has_perm
from crm.zetom.models import (
    Oferta, OfertaClientLink, RequestClientLink, RequestMain, Wniosek,
    WniosekClientLink, Zlecenie, ZlecenieClientLink,
)
# claude — reuse the normalization helpers the duplicate matchers already use,
# so "Suggested · pasuje do kontaktu" scores contact fields the same way the VW does.
from crm.zetom.services.duplicate_matcher import (
    _email_domain, _norm, _phone_str,
)


# claude — /admin/clients/company/ is the stock Django changelist for Company:
# a raw checkbox table that the unified Klienci list replaced. Unfold still
# links it from the breadcrumbs, and it was reachable from the dashboard and
# the company card's "Wróć", so users kept landing back on the old screen.
# Sent to the Klienci list filtered to firms — the same rows, the designed way.
#
# Mounted in config/urls.py ahead of admin.site.urls; a plain view rather than
# RedirectView because the target carries a query string.
def company_changelist_redirect(request):
    return redirect(f"{reverse('admin:clients_client_changelist')}?rodzaj=firmy")


# claude — Company keeps its postal address in street/post_code/city/country;
# `comments` only holds the free-text address the pre-normalization backfill
# dumped there (migration 0007). Prefer the structured fields, fall back to
# the backfilled blob so old rows still autofill something sensible.
def _company_address(company) -> str:
    city_line = " ".join(filter(None, (company.post_code, company.city)))
    parts = (company.street, city_line, company.country)
    address = ", ".join(p.strip() for p in parts if p and p.strip())
    return address or company.comments or ""


# claude — раньше эти эндпоинты отвечали без аутентификации (URL смонтирован
# вне /admin/). Любой аноним мог дёрнуть `/clients/search/?q=A` и выгрузить
# список клиентов. Закрываем: требуем login + permission view_clients.
@method_decorator(login_required, name="dispatch")
class ClientSearchView(View):
    def get(self, request):
        if not user_has_perm(request.user, "view_clients"):
            return JsonResponse({"results": []}, status=403)

        q = request.GET.get("q", "").strip()

        if not q:
            return JsonResponse({"results": []})

        query_terms = [q]
        if "(" in q and ")" in q:
            maybe_nip = q[q.rfind("(") + 1:q.rfind(")")].strip()
            if maybe_nip:
                query_terms.append(maybe_nip)

        # claude — Company-aware search: match Client by first/last name AND by linked
        # Company name/nip; derive label/company_nip/address from first linked company.
        query = Q()
        for term in set(query_terms):
            query |= Q(first_name__icontains=term)
            query |= Q(last_name__icontains=term)
            query |= Q(company_links__company__name__icontains=term)
            query |= Q(company_links__company__nip__icontains=term)

        clients = (
            Client.objects.filter(query)
            .prefetch_related("company_links__company")
            .distinct()
            .order_by("last_name")[:20]
        )

        # claude — .first() clones the manager's queryset (order_by('pk')[:1]),
        # which bypasses the prefetch_related cache and re-hits the DB per row.
        # .all() on a manager with a populated prefetch cache returns the
        # cached, already-evaluated queryset, so indexing it is free.
        def _company_of(c):
            links = list(c.company_links.all())
            return links[0].company if links else None

        results = []
        for c in clients:
            company = _company_of(c)
            label = (
                (company.name if company else None)
                or f"{c.first_name or ''} {c.last_name or ''}".strip()
                or f"Client #{c.id}"
            )
            results.append({
                "id": c.id,
                "label": label,
                # claude — client_search.js prefills the person fields of a
                # request form from the picked row, so they have to be in the
                # payload; before, the JS read keys the endpoint never sent.
                "first_name": c.first_name or "",
                "last_name": c.last_name or "",
                "email": c.email,
                "phone": c.phone.as_international if c.phone else "",
                "company_name": company.name if company else "",
                "company_nip": company.nip if company else "",
                "address": _company_address(company) if company else "",
            })
        return JsonResponse({"results": results})


# claude — то же, что для ClientSearchView: autofill раньше работал
# анонимно. Закрываем тем же permission'ом (view_clients).
@login_required
def client_autofill(request):
    if not user_has_perm(request.user, "view_clients"):
        return JsonResponse({"error": "forbidden"}, status=403)
    nip = request.GET.get("nip")
    if not nip:
        return JsonResponse({"error": "no_nip"}, status=400)

    # claude — autofill now resolves Company by NIP (NIP moved from Client to
    # Company), and pulls the first linked person.
    company = Company.objects.filter(nip=nip).first()
    if company is None:
        return JsonResponse({"exists": False})
    link = company.person_links.first()
    person = link.person if link else None
    return JsonResponse({
        "exists": True,
        "first_name": person.first_name if person else "",
        "last_name": person.last_name if person else "",
        "company_name": company.name,
        "company_nip": company.nip,
        "email": (person.email if person else "") or "",
        "phone": person.phone.as_international if (person and person.phone) else "",
        "address": _company_address(company),
    })


# claude — shared field guards for the JSON write endpoints below. They all
# take raw POST strings and assign straight to the model, so anything not
# checked here lands in the DB unvalidated (ModelForm.full_clean never runs on
# these paths — the cards bypass forms entirely).
#
# Empty is always allowed (every field guarded here is optional); only a
# non-empty invalid value is rejected.
def _invalid_email_error(email: str):
    if not email:
        return None
    try:
        validate_email(email)
    except ValidationError:
        return gettext("Nieprawidłowy adres e-mail.")
    return None


# claude — PhoneNumberField stores whatever it is handed: "not-a-phone" became
# an invalid PhoneNumber whose as_international rendered as the string "None",
# and "12345" was silently saved as "+48 12345". to_python() parses against
# PHONENUMBER_DEFAULT_REGION (PL), is_valid() rejects both.
def _invalid_phone_error(phone: str):
    if not phone:
        return None
    number = phone_to_python(phone)
    if number is None or not number.is_valid():
        return gettext("Nieprawidłowy numer telefonu.")
    return None


# claude — NIP: normalize_nip() strips separators/PL prefix, validate_nip()
# checks the mod-11 checksum. Returns (normalized_nip_or_None, error_or_None).
#
# `unchanged_from` is the value already stored on the row. The intake path
# (services.create_person_with_company, called from the zetom admin) normalizes
# a NIP typed on a request but never checks its checksum, so companies carrying
# a bad-checksum NIP already exist in the DB. Re-validating a value the user
# never touched would make those cards impossible to save at all — even to fix
# an unrelated field. So a NIP is only checksum-checked when it actually
# changes; editing it means accepting the check.
def _clean_nip(raw: str, unchanged_from: str = None):
    if not raw:
        return None, None
    if unchanged_from and raw.strip() == unchanged_from:
        return unchanged_from, None
    try:
        nip = normalize_nip(raw)
    except ValidationError as exc:
        return None, " ".join(exc.messages)
    if nip == unchanged_from:
        return nip, None
    try:
        validate_nip(nip)
    except ValidationError as exc:
        return None, " ".join(exc.messages)
    return nip, None


# claude — Osoby kontaktowe panel backend (Company detail card). Mounted under
# CompanyAdmin.get_urls so admin_view enforces staff auth; edit_clients is
# re-checked on top. add/edit return the row JSON the panel's JS needs to
# redraw the table row without a full page reload; delete only drops the link
# (the underlying Client/person is never deleted from here).
def company_person_row(link):
    person = link.person
    return {
        "link_pk": link.pk,
        "imie": person.first_name or "",
        "nazwisko": person.last_name or "",
        "email": person.email or "",
        "telefon": person.phone.as_international if person.phone else "",
        "stanowisko": link.position or "",
        "glowny": link.is_primary,
    }


# claude
@login_required
@require_POST
def company_person_add(request, pk):
    if not user_has_perm(request.user, "edit_clients"):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)

    company = get_object_or_404(Company, pk=pk)
    is_primary = bool(request.POST.get("is_primary"))
    email = request.POST.get("email", "").strip()
    phone = request.POST.get("phone", "").strip()
    error = _invalid_email_error(email) or _invalid_phone_error(phone)
    if error:
        return JsonResponse({"ok": False, "error": error}, status=400)

    with transaction.atomic():
        person = Client.objects.create(
            first_name=request.POST.get("first_name", "").strip(),
            last_name=request.POST.get("last_name", "").strip(),
            email=email,
            phone=phone or None,
        )
        if is_primary:
            company.person_links.filter(is_primary=True).update(is_primary=False)
        link = CompanyPersonLink.objects.create(
            company=company, person=person,
            position=request.POST.get("position", "").strip(),
            is_primary=is_primary,
            linked_by=request.user,
        )
    return JsonResponse({"ok": True, "row": company_person_row(link)})


# claude
@login_required
@require_POST
def company_person_edit(request, pk, link_pk):
    if not user_has_perm(request.user, "edit_clients"):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)

    company = get_object_or_404(Company, pk=pk)
    link = get_object_or_404(CompanyPersonLink, pk=link_pk, company=company)
    is_primary = bool(request.POST.get("is_primary"))
    email = request.POST.get("email", "").strip()
    phone = request.POST.get("phone", "").strip()
    error = _invalid_email_error(email) or _invalid_phone_error(phone)
    if error:
        return JsonResponse({"ok": False, "error": error}, status=400)

    with transaction.atomic():
        person = link.person
        person.first_name = request.POST.get("first_name", "").strip()
        person.last_name = request.POST.get("last_name", "").strip()
        person.email = email
        person.phone = phone or None
        person.save()

        if is_primary:
            company.person_links.exclude(pk=link.pk).filter(is_primary=True).update(is_primary=False)
        link.position = request.POST.get("position", "").strip()
        link.is_primary = is_primary
        link.save()

    return JsonResponse({"ok": True, "row": company_person_row(link)})


# claude
@login_required
@require_POST
def company_person_delete(request, pk, link_pk):
    if not user_has_perm(request.user, "edit_clients"):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)

    company = get_object_or_404(Company, pk=pk)
    # Removes only the link row — the person (Client) is left intact.
    CompanyPersonLink.objects.filter(pk=link_pk, company=company).delete()
    return JsonResponse({"ok": True})


# claude — Dane podstawowe / Dane szczegółowe save endpoint for the Company
# card. CompanyAdmin.change_view renders a fully custom template and never
# builds a ModelForm, so before this endpoint existed the two "Edytuj" buttons
# had nothing to call and a Company could only be edited from the shell.
#
# One endpoint, two field sets: the POST carries `section`, and only that
# section's fields are read — a partial POST can never blank the other panel.
_COMPANY_SECTIONS = {
    "podstawowe": ("name", "nip", "regon", "type_supplier"),
    "szczegolowe": (
        "country", "city", "voivodeship", "post_code", "street", "email", "phone",
    ),
}


# claude — per-field cleaning for company_save. Returns (values, error).
# `company` is None when creating (the Add Client modal reuses this helper for
# both sections at once), an instance when editing one panel of an existing one.
def _clean_company_section(section: str, post, company=None):
    values = {f: post.get(f, "").strip() for f in _COMPANY_SECTIONS[section]}

    if section == "podstawowe":
        if not values["name"]:
            return None, gettext("Nazwa firmy jest wymagana.")
        nip, error = _clean_nip(
            values["nip"], unchanged_from=company.nip if company else None,
        )
        if error:
            return None, error
        # claude — uniq_company_nip is a partial UniqueConstraint; checking it
        # here turns a 500 IntegrityError into a readable modal error.
        clash = Company.objects.filter(nip=nip) if nip else Company.objects.none()
        if company is not None and company.pk:
            clash = clash.exclude(pk=company.pk)
        if clash.exists():
            return None, gettext("Firma z tym NIP-em już istnieje.")
        values["nip"] = nip
        if values["type_supplier"] and values["type_supplier"] not in SupplierType.values:
            return None, gettext("Nieznany typ dostawcy.")
    else:
        error = (
            _invalid_email_error(values["email"])
            or _invalid_phone_error(values["phone"])
        )
        if error:
            return None, error
        values["phone"] = values["phone"] or None

    return values, None


# claude
@login_required
@require_POST
def company_save(request, pk):
    if not user_has_perm(request.user, "edit_clients"):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)

    section = request.POST.get("section", "")
    if section not in _COMPANY_SECTIONS:
        return JsonResponse({"ok": False, "error": "bad_section"}, status=400)

    company = get_object_or_404(Company, pk=pk)
    values, error = _clean_company_section(section, request.POST, company)
    if error:
        return JsonResponse({"ok": False, "error": error}, status=400)

    for field, value in values.items():
        setattr(company, field, value)
    company.save(update_fields=list(values))
    return JsonResponse({"ok": True})


# claude — Dane osobowe save endpoint for the Person (Osoba) card (mOsobowe
# modal). Only touches first_name/last_name/phone/email — company data lives
# on Company now, never on Client.
@login_required
@require_POST
def person_save(request, pk):
    if not user_has_perm(request.user, "edit_clients"):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)

    person = get_object_or_404(Client, pk=pk)
    email = request.POST.get("email", "").strip()
    phone = request.POST.get("phone", "").strip()
    error = _invalid_email_error(email) or _invalid_phone_error(phone)
    if error:
        return JsonResponse({"ok": False, "error": error}, status=400)

    person.first_name = request.POST.get("first_name", "").strip()
    person.last_name = request.POST.get("last_name", "").strip()
    person.email = email
    person.phone = phone or None
    person.save()

    return JsonResponse({
        "ok": True,
        "first_name": person.first_name or "",
        "last_name": person.last_name or "",
        "phone": person.phone.as_international if person.phone else "",
        "email": person.email or "",
    })


# claude — Firmy panel on the Person card: search + attach + edit + detach.
# All four mounted on ClientAdmin.get_urls (admin_view enforces staff auth;
# RBAC re-checked here). Search feeds the picker; attach creates the
# CompanyPersonLink (idempotent); edit/detach act on an existing link and
# never touch the Company or the Client itself.
@login_required
def company_search(request, pk):
    if not user_has_perm(request.user, "view_clients"):
        return JsonResponse({"results": []}, status=403)

    person = get_object_or_404(Client, pk=pk)
    q = request.GET.get("q", "").strip()
    qs = Company.objects.exclude(person_links__person=person)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(nip__icontains=q))
    qs = qs.order_by("name")[:8]
    return JsonResponse({
        "results": [{"id": c.pk, "name": c.name, "nip": c.nip or ""} for c in qs]
    })


# claude
@login_required
@require_POST
def attach_company(request, pk):
    if not user_has_perm(request.user, "edit_clients"):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)

    person = get_object_or_404(Client, pk=pk)
    company = get_object_or_404(Company, pk=request.POST.get("company_id"))
    CompanyPersonLink.objects.get_or_create(
        company=company, person=person, defaults={"linked_by": request.user},
    )
    return JsonResponse({"ok": True})


# claude — edit the link itself (stanowisko / główny kontakt), not the person.
@login_required
@require_POST
def company_link_save(request, pk, link_pk):
    if not user_has_perm(request.user, "edit_clients"):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)

    person = get_object_or_404(Client, pk=pk)
    link = get_object_or_404(CompanyPersonLink, pk=link_pk, person=person)
    is_primary = bool(request.POST.get("is_primary"))

    with transaction.atomic():
        # claude — "główny kontakt" is per-Company, so clearing the flag has to
        # look at that company's other links, not at this person's.
        if is_primary:
            CompanyPersonLink.objects.filter(
                company_id=link.company_id, is_primary=True,
            ).exclude(pk=link.pk).update(is_primary=False)
        link.position = request.POST.get("position", "").strip()
        link.is_primary = is_primary
        link.save(update_fields=["position", "is_primary"])

    return JsonResponse({"ok": True})


# claude
@login_required
@require_POST
def detach_company(request, pk, link_pk):
    if not user_has_perm(request.user, "edit_clients"):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)

    person = get_object_or_404(Client, pk=pk)
    # Removes only the link row — the Company and the person both stay.
    CompanyPersonLink.objects.filter(pk=link_pk, person=person).delete()
    return JsonResponse({"ok": True})


# claude — Add Client modal backend (see design_handoff_add_client). Three
# endpoints mounted under ClientAdmin.get_urls so admin_view enforces staff
# auth; each re-checks the RBAC code on top (edit_clients to create,
# view_clients to search/suggest). None of them ever scans a full table.
#
# (request model, link model, type key, badge text). Order = display order.
_SUGGEST_MODELS = [
    (RequestMain, RequestClientLink, "main", "M"),
    (Oferta, OfertaClientLink, "oferta", "OF"),
    (Zlecenie, ZlecenieClientLink, "zlecenie", "ZL"),
    (Wniosek, WniosekClientLink, "wniosek", "WN"),
]

# claude — what the modal can create. "firma" writes a Company, "osoba" a
# Client; the request picker is narrowed per kind (see _models_for_kind).
_KINDS = ("osoba", "firma")


# claude — a Company can only be attached to a RequestMain: `company` is a FK
# that exists on RequestMain alone. Oferta/Zlecenie/Wniosek reach a client only
# through their person M2M, so they are offered for "osoba" and refused for
# "firma" — enforced here, not just hidden in the UI.
def _models_for_kind(kind: str):
    if kind == "firma":
        return [row for row in _SUGGEST_MODELS if row[0] is RequestMain]
    return _SUGGEST_MODELS


# claude
def _req_name(obj) -> str:
    """Person/company display name for a request row."""
    return (
        obj.company_name
        or " ".join(filter(None, (obj.first_name, obj.last_name)))
        or f"#{obj.pk}"
    )


# claude
def _req_result(obj, type_key, badge, match=None) -> dict:
    row = {"pk": obj.pk, "type": type_key, "badge": badge, "label": _req_name(obj)}
    if match:
        row["match"] = match
    return row


# claude — keep RequestMain queries clear of dead requests; the child docs
# (Oferta/Zlecenie/Wniosek) have no request-level lifecycle status to skip.
def _live_qs(model):
    qs = model.objects.all()
    if model is RequestMain:
        qs = qs.exclude(status__in=[RequestStatus.cancelled, RequestStatus.deleted])
    return qs


# claude — which contact field matched, mirroring the duplicate matcher's
# signal priority (phone > NIP > email > name).
def _match_reason(obj, phone, email, nip, name_tokens):
    if phone and _phone_str(obj.phone) == phone:
        return gettext("dopasowanie po telefonie")
    if nip and _norm(obj.company_nip) == nip:
        return gettext("dopasowanie po NIP")
    if email and _norm(obj.email) == _norm(email):
        return gettext("dopasowanie po e-mailu")
    return gettext("dopasowanie po nazwie")


# claude — wide-net Q from the entered contact fields (same shape as
# duplicate_finder._prefilter), capped per model by the caller.
def _suggest_q(phone, email, nip, name_tokens):
    q = Q()
    if phone:
        q |= Q(phone=phone)
    if email:
        q |= Q(email__iexact=email)
        domain = _email_domain(email)
        if domain:
            q |= Q(email__iendswith=f"@{domain}")
    if nip:
        q |= Q(company_nip__icontains=nip)
    for tok in name_tokens:
        q |= Q(first_name__icontains=tok)
        q |= Q(last_name__icontains=tok)
        q |= Q(company_name__icontains=tok)
    return q


# claude
@login_required
def request_suggest(request):
    if not user_has_perm(request.user, "view_clients"):
        return JsonResponse({"suggested": [], "recent": []}, status=403)

    models = _models_for_kind(request.GET.get("kind", ""))
    phone = request.GET.get("phone", "").strip()
    email = request.GET.get("email", "").strip()
    nip = _norm(request.GET.get("nip", ""))
    name = request.GET.get("name", "").strip()
    # drop single-char noise tokens so "a b" doesn't match everything
    name_tokens = {t for t in name.split() if len(t) >= 2}

    has_contact = bool(phone or email or nip or name_tokens)
    q = _suggest_q(phone, email, nip, name_tokens) if has_contact else None

    suggested = []
    seen = set()
    if q is not None:
        for model, _link, type_key, badge in models:
            rows = _live_qs(model).filter(q).order_by("-created_at")[:3]
            for obj in rows:
                seen.add((type_key, obj.pk))
                suggested.append(_req_result(
                    obj, type_key, badge,
                    match=_match_reason(obj, phone, email, nip, name_tokens),
                ))

    recent = []
    for model, _link, type_key, badge in models:
        rows = _live_qs(model).order_by("-created_at")[:2 + len(seen)]
        added = 0
        for obj in rows:
            if (type_key, obj.pk) in seen:
                continue
            recent.append(_req_result(obj, type_key, badge))
            added += 1
            if added >= 2:
                break

    return JsonResponse({"suggested": suggested, "recent": recent})


# claude
@login_required
def request_search(request):
    if not user_has_perm(request.user, "view_clients"):
        return JsonResponse({"results": [], "total": 0}, status=403)

    models = _models_for_kind(request.GET.get("kind", ""))
    q = request.GET.get("q", "").strip()
    if not q:
        return JsonResponse({"results": [], "total": 0})

    try:
        limit = max(1, min(int(request.GET.get("limit", 8)), 20))
    except (TypeError, ValueError):
        limit = 8

    query = (
        Q(first_name__icontains=q)
        | Q(last_name__icontains=q)
        | Q(company_name__icontains=q)
    )
    if q.isdigit():
        query |= Q(pk=int(q))

    total = 0
    results = []
    for model, _link, type_key, badge in models:
        matched = _live_qs(model).filter(query)
        total += matched.count()
        for obj in matched.order_by("-pk")[:limit]:
            results.append(_req_result(obj, type_key, badge))

    return JsonResponse({"results": results[:limit], "total": total})


# claude — resolve the optional "Powiąż zgłoszenie" selection into the request
# object to attach. Returns (row_or_None, error): None/None means the user
# simply didn't pick anything, which is the normal case.
def _resolve_request_pick(kind: str, req_type: str, req_pk: str):
    if not req_pk:
        return None, None
    row = next(
        (r for r in _models_for_kind(kind) if r[2] == req_type), None,
    )
    if row is None:
        # either an unknown type key, or a child document picked for a firm —
        # only RequestMain carries the Company FK.
        return None, gettext("Tego zgłoszenia nie można powiązać z tym rodzajem klienta.")
    model = row[0]
    obj = _live_qs(model).filter(pk=req_pk).first()
    if obj is None:
        return None, gettext("Nie znaleziono wybranego zgłoszenia.")
    return (obj, row[1]), None


# claude — Add Client create endpoint. One POST behind the modal: `kind`
# decides which table gets written (Company for "firma", Client for "osoba"),
# and every field guard is the same helper the edit modals already use, so a
# value rejected here is rejected there too. Creation and the optional request
# link share one transaction.
@login_required
@require_POST
def client_create(request):
    if not user_has_perm(request.user, "edit_clients"):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)

    kind = request.POST.get("kind", "")
    if kind not in _KINDS:
        return JsonResponse({"ok": False, "error": "bad_kind"}, status=400)

    pick, error = _resolve_request_pick(
        kind, request.POST.get("req_type", ""), request.POST.get("req_pk", "").strip(),
    )
    if error:
        return JsonResponse({"ok": False, "error": error}, status=400)

    if kind == "firma":
        values = {}
        for section in _COMPANY_SECTIONS:
            section_values, error = _clean_company_section(section, request.POST)
            if error:
                return JsonResponse({"ok": False, "error": error}, status=400)
            values.update(section_values)
    else:
        email = request.POST.get("email", "").strip()
        phone = request.POST.get("phone", "").strip()
        error = _invalid_email_error(email) or _invalid_phone_error(phone)
        if error:
            return JsonResponse({"ok": False, "error": error}, status=400)
        values = {
            "first_name": request.POST.get("first_name", "").strip() or None,
            "last_name": request.POST.get("last_name", "").strip() or None,
            "email": email or None,
            "phone": phone or None,
        }
        if not (values["first_name"] or values["last_name"]):
            return JsonResponse(
                {"ok": False, "error": gettext("Podaj imię lub nazwisko.")}, status=400,
            )

    with transaction.atomic():
        if kind == "firma":
            obj = Company.objects.create(**values)
            url_name = "admin:clients_company_change"
        else:
            obj = Client.objects.create(**values)
            url_name = "admin:clients_client_change"

        if pick is not None:
            req_obj, link_model = pick
            error = _attach_new_client(kind, obj, req_obj, link_model, request.user)
            if error:
                # claude — raising would need a savepoint dance; the row is
                # small and nothing else has happened yet, so just unwind.
                transaction.set_rollback(True)
                return JsonResponse({"ok": False, "error": error}, status=400)

    return JsonResponse({"ok": True, "url": reverse(url_name, args=[obj.pk])})


# claude — attach the freshly created client to the picked request. A firm goes
# into RequestMain.company (FK), a person into the request's client M2M.
def _attach_new_client(kind, obj, req_obj, link_model, user):
    if kind == "firma":
        # claude — never silently repoint a request that already belongs to
        # another firm; that would quietly rewrite existing data.
        if req_obj.company_id and req_obj.company_id != obj.pk:
            return gettext("To zgłoszenie jest już powiązane z inną firmą.")
        req_obj.company = obj
        req_obj.save(update_fields=["company"])
        return None
    link_model.objects.get_or_create(
        request=req_obj, client=obj, defaults={"linked_by": user},
    )
    return None
