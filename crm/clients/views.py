from django.http import JsonResponse
from django.views import View
from django.db.models import Q

from crm.clients.models import Client



class ClientSearchView(View):
    def get(self, request):
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



def client_autofill(request):
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
