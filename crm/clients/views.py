from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View

from crm.clients.models import Client
from crm.users.utils import user_has_perm


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
                    "phone": c.phone.as_national if c.phone else "",
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
            "phone": client.phone.as_national if client.phone else "",
            "address": client.address,
        })
    except Client.DoesNotExist:
        return JsonResponse({"exists": False})
