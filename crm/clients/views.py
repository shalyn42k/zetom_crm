from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext, gettext_lazy as _
from django.views import View
from django.views.decorators.http import require_POST

from crm.clients.forms import ClientForm
from crm.clients.models import Client, Company, CompanyPersonLink
from crm.status_manager.services.statuses import RequestStatus
from crm.users.utils import user_has_perm
from crm.zetom.models import (
    Oferta, OfertaClientLink, RequestClientLink, RequestMain, Wniosek,
    WniosekClientLink, Zlecenie, ZlecenieClientLink,
)
# claude — reuse the normalization helpers the duplicate matchers already use,
# so "Suggested · matches contact" scores contact fields the same way the VW does.
from crm.zetom.services.duplicate_matcher import (
    _email_domain, _norm, _phone_str,
)


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
                "email": c.email,
                "phone": c.phone.as_international if c.phone else "",
                "company_nip": company.nip if company else "",
                "address": company.comments if company else "",
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
        "address": company.comments or "",
    })


# claude — attach/detach/search for the Client Detail request tabs.
# Wired into ClientAdmin.get_urls so admin_view enforces staff auth; the
# edit_clients RBAC code is checked explicitly on top (mirrors ClientAdmin).
#
# Each entry: (request model, link model, id prefix shown in search results).
_TYPE_MAP = {
    "main": (RequestMain, RequestClientLink, ""),
    "oferta": (Oferta, OfertaClientLink, "OF-"),
    "zlecenie": (Zlecenie, ZlecenieClientLink, "ZL-"),
    "wniosek": (Wniosek, WniosekClientLink, "WN-"),
}


# claude
def _request_label(obj, prefix: str) -> str:
    name = obj.company_name or " ".join(filter(None, (obj.first_name, obj.last_name)))
    base = f"{prefix}{obj.pk}"
    return f"{base} · {name}" if name else base


# claude
@login_required
@require_POST
def client_attach(request, pk, type):
    if not user_has_perm(request.user, "edit_clients"):
        return JsonResponse({"error": "forbidden"}, status=403)
    if type not in _TYPE_MAP:
        return HttpResponseBadRequest("bad type")

    client = get_object_or_404(Client, pk=pk)
    model, link_model, _prefix = _TYPE_MAP[type]
    req_pk = request.POST.get("req_pk")
    req_obj = get_object_or_404(model, pk=req_pk)

    link_model.objects.get_or_create(
        request=req_obj, client=client, defaults={"linked_by": request.user},
    )
    messages.success(request, _("Request attached to client."))
    return redirect("admin:clients_client_change", pk)


# claude
@login_required
@require_POST
def client_detach(request, pk, type, req_pk):
    if not user_has_perm(request.user, "edit_clients"):
        return JsonResponse({"error": "forbidden"}, status=403)
    if type not in _TYPE_MAP:
        return HttpResponseBadRequest("bad type")

    client = get_object_or_404(Client, pk=pk)
    _model, link_model, _prefix = _TYPE_MAP[type]
    # Removes only the link row — the request itself is left intact.
    link_model.objects.filter(request_id=req_pk, client=client).delete()
    messages.success(request, _("Request detached from client."))
    return redirect("admin:clients_client_change", pk)


# claude
def client_attach_search(request, pk, type):
    if not user_has_perm(request.user, "edit_clients"):
        return JsonResponse({"results": []}, status=403)
    if type not in _TYPE_MAP:
        return HttpResponseBadRequest("bad type")

    client = get_object_or_404(Client, pk=pk)
    model, _link_model, prefix = _TYPE_MAP[type]
    q = request.GET.get("q", "").strip()
    if not q:
        return JsonResponse({"results": []})

    query = (
        Q(company_name__icontains=q)
        | Q(first_name__icontains=q)
        | Q(last_name__icontains=q)
    )
    if q.isdigit():
        query |= Q(pk=int(q))

    # exclude already-linked requests (clients M2M)
    qs = model.objects.filter(query).exclude(clients=client).order_by("-pk")[:8]

    return JsonResponse({
        "results": [{"pk": obj.pk, "label": _request_label(obj, prefix)} for obj in qs]
    })


# claude — Add Client modal backend (see design_handoff_add_client).
# Three endpoints mounted under ClientAdmin.get_urls so admin_view enforces
# staff auth; each re-checks the RBAC code on top (edit_clients to create,
# view_clients to search/suggest). None of them ever scans a full table.
#
# (request model, type key, badge text, CSS badge class). Order = display order.
_SUGGEST_MODELS = [
    (RequestMain, "main", "M", "m"),
    (Oferta, "oferta", "OF", "of"),
    (Zlecenie, "zlecenie", "ZL", "zl"),
    (Wniosek, "wniosek", "WN", "wn"),
]


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
        return gettext("phone match")
    if nip and _norm(obj.company_nip) == nip:
        return gettext("nip match")
    if email and _norm(obj.email) == _norm(email):
        return gettext("email match")
    return gettext("name match")


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
        for model, type_key, badge, _cls in _SUGGEST_MODELS:
            rows = _live_qs(model).filter(q).order_by("-created_at")[:3]
            for obj in rows:
                seen.add((type_key, obj.pk))
                suggested.append(_req_result(
                    obj, type_key, badge,
                    match=_match_reason(obj, phone, email, nip, name_tokens),
                ))

    recent = []
    for model, type_key, badge, _cls in _SUGGEST_MODELS:
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
    for model, type_key, badge, _cls in _SUGGEST_MODELS:
        matched = _live_qs(model).filter(query)
        total += matched.count()
        for obj in matched.order_by("-pk")[:limit]:
            results.append(_req_result(obj, type_key, badge))

    return JsonResponse({"results": results[:limit], "total": total})


# claude
@login_required
@require_POST
def client_create(request):
    if not user_has_perm(request.user, "edit_clients"):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)

    form = ClientForm(request.POST)
    if not form.is_valid():
        return JsonResponse(
            {"ok": False, "errors": form.errors.get_json_data()}, status=422
        )

    client = form.save()

    link_type = request.POST.get("link_type")
    link_req_pk = request.POST.get("link_req_pk")
    if link_type and link_req_pk and link_type in _TYPE_MAP:
        model, link_model, _prefix = _TYPE_MAP[link_type]
        req_obj = get_object_or_404(model, pk=link_req_pk)
        link_model.objects.get_or_create(
            request=req_obj, client=client,
            defaults={"linked_by": request.user},
        )

    return JsonResponse({
        "ok": True,
        "redirect_url": reverse("admin:clients_client_change", args=[client.pk]),
    })


# claude — Osoby kontaktowe panel backend (Company detail card, Phase 3a
# Task 2). Mounted under CompanyAdmin.get_urls so admin_view enforces staff
# auth; edit_clients is re-checked on top, mirroring the Client endpoints
# above. add/edit return the row JSON the panel's JS needs to redraw the
# table row without a full page reload; delete only drops the link (the
# underlying Client/person is never deleted from here).
# claude — shared email guard for the add/edit endpoints below; empty email
# is allowed (field is optional), only a non-empty invalid value is rejected.
def _invalid_email_error(email: str):
    if not email:
        return None
    try:
        validate_email(email)
    except ValidationError:
        return gettext("Nieprawidłowy adres e-mail.")
    return None


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
    error = _invalid_email_error(email)
    if error:
        return JsonResponse({"ok": False, "error": error}, status=400)

    with transaction.atomic():
        person = Client.objects.create(
            first_name=request.POST.get("first_name", "").strip(),
            last_name=request.POST.get("last_name", "").strip(),
            email=email,
            phone=request.POST.get("phone", "").strip() or None,
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
    error = _invalid_email_error(email)
    if error:
        return JsonResponse({"ok": False, "error": error}, status=400)

    with transaction.atomic():
        person = link.person
        person.first_name = request.POST.get("first_name", "").strip()
        person.last_name = request.POST.get("last_name", "").strip()
        person.email = email
        person.phone = request.POST.get("phone", "").strip() or None
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
