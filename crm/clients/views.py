from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext, gettext_lazy as _
from django.views import View
from django.views.decorators.http import require_POST

from crm.clients.forms import ClientForm
from crm.clients.models import Client
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

        query = Q()
        for term in set(query_terms):
            query |= Q(company_name__icontains=term)
            query |= Q(company_nip__icontains=term)
            query |= Q(first_name__icontains=term)
            query |= Q(last_name__icontains=term)

        clients = Client.objects.filter(query).order_by("company_name", "last_name")[:20]

        return JsonResponse({
            "results": [
                {
                    "id": c.id,
                    "label": c.company_name or f"{c.first_name} {c.last_name}" or f"Client #{c.id}",
                    "email": c.email,
                    "phone": c.phone.as_international if c.phone else "",
                    "company_nip": c.company_nip,
                    "address": c.address,
                }
                for c in clients
            ]
        })



# claude — то же, что для ClientSearchView: autofill раньше работал
# анонимно. Закрываем тем же permission'ом (view_clients).
@login_required
def client_autofill(request):
    if not user_has_perm(request.user, "view_clients"):
        return JsonResponse({"error": "forbidden"}, status=403)
    nip = request.GET.get("nip")
    if not nip:
        return JsonResponse({"error": "no_nip"}, status=400)

    try:
        client = Client.objects.get(company_nip=nip)
        return JsonResponse({
            "exists": True,
            "first_name": client.first_name,
            "last_name": client.last_name,
            "company_name": client.company_name,
            "company_nip": client.company_nip,
            "email": client.email,
            "phone": client.phone.as_international if client.phone else "",
            "address": client.address,
        })
    except Client.DoesNotExist:
        return JsonResponse({"exists": False})


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
