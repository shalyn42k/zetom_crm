from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from crm.status_manager.services.statuses import RequestStatus
from crm.users.utils import user_has_perm
from crm.zetom.models import DepartmentsVariants, RequestMain

from . import views
from .forms import ClientForm
from .models import (
    Client, ClientInteraction, ClientType, Company, CompanyPersonLink,
)
from .services import build_request_rows, get_client_request_summary

# claude — Phase 3a Task 3: RequestStatus → the four status-badge CSS classes
# the design defines (company_card.css `.st.*`). RequestMain's real statuses
# don't map 1:1 onto the handoff's Aktywne/Oczekuje/Wygrane/Zamknięte set (no
# "won" concept here), so closed/inactive/cancelled/deleted all fall back to
# the neutral "zamkniete" bucket.
_ZGLOSZENIE_STATUS_CLASS = {
    RequestStatus.active: "aktywne",
    RequestStatus.open: "oczekuje",
    RequestStatus.closed: "zamkniete",
    RequestStatus.inactive: "zamkniete",
    RequestStatus.cancelled: "zamkniete",
    RequestStatus.deleted: "zamkniete",
}


# claude — human, non-technical row title for a RequestMain on the Company
# card (README §"НЕ делать": no raw model names like RequestMain in UI).
def _zgloszenie_label(req: RequestMain) -> str:
    return _("Zgłoszenie nr %(pk)s / %(year)s") % {
        "pk": req.pk, "year": req.created_at.year,
    }


# claude — first department code of a request → its PL label (ArrayField).
def _zgloszenie_dept_label(codes) -> str:
    if not codes:
        return ""
    labels = dict(DepartmentsVariants.choices)
    return str(labels.get(codes[0], codes[0]))


# БАГ-9 + БАГ-10: inline история контактов прямо в карточке клиента
class ClientInteractionInline(admin.TabularInline):
    model = ClientInteraction
    extra = 0
    fields = ("contacted_at", "channel", "contact_person", "contacted_by", "summary", "request")
    autocomplete_fields = ("request",)
    readonly_fields = ("created_at",)
    ordering = ("-contacted_at",)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = (
        "first_name", "last_name", "company_name", "email", "phone",
        "client_type",
        # claude
        "col_requests", "col_ofertas", "col_zlecenia", "col_wnioski",
    )
    search_fields = ("first_name", "last_name", "company_name", "email", "phone")
    inlines = [ClientInteractionInline]
    # claude
    list_filter = ["client_type"]

    # claude — custom List + Detail screens (see design_handoff_client_pages).
    change_list_template = "admin/clients/client/change_list.html"
    change_form_template = "admin/clients/client/change_form.html"

    # claude
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            _request_count=Count("requests", distinct=True),
            _oferta_count=Count("ofertas", distinct=True),
            _zlecenie_count=Count("zlecenia", distinct=True),
            _wniosek_count=Count("wnioski", distinct=True),
        )

    # claude
    @admin.display(description=_("Requests"), ordering="_request_count")
    def col_requests(self, obj):
        return obj._request_count

    # claude
    @admin.display(description=_("Offers"), ordering="_oferta_count")
    def col_ofertas(self, obj):
        return obj._oferta_count

    # claude
    @admin.display(description=_("Orders"), ordering="_zlecenie_count")
    def col_zlecenia(self, obj):
        return obj._zlecenie_count

    # claude
    @admin.display(description=_("Applications"), ordering="_wniosek_count")
    def col_wnioski(self, obj):
        return obj._wniosek_count

    # claude — раньше тут не было гейтов: любой is_staff видел и менял
    # базу клиентов. Привязываем к RBAC-кодам view_clients / edit_clients
    # (см. crm/users/signals.py). superuser получает всё через user_has_perm.
    def has_module_permission(self, request):
        return user_has_perm(request.user, "view_clients")

    def has_view_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_clients")

    def has_add_permission(self, request):
        return user_has_perm(request.user, "edit_clients")

    def has_change_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_clients")

    def has_delete_permission(self, request, obj=None):
        return user_has_perm(request.user, "delete_clients")

    # claude — attach/detach/search endpoints for the Detail request tabs.
    # Mounted under the admin so admin_view enforces auth; the views also
    # re-check edit_clients. Names live in the admin: namespace.
    def get_urls(self):
        urls = super().get_urls()
        view = self.admin_site.admin_view
        custom = [
            path(
                "<int:pk>/attach/<str:type>/",
                view(views.client_attach),
                name="clients_client_attach",
            ),
            path(
                "<int:pk>/detach/<str:type>/<int:req_pk>/",
                view(views.client_detach),
                name="clients_client_detach",
            ),
            path(
                "<int:pk>/attach-search/<str:type>/",
                view(views.client_attach_search),
                name="clients_client_attachsearch",
            ),
            # claude — Add Client modal endpoints (see design_handoff_add_client).
            path(
                "create/",
                view(views.client_create),
                name="clients_client_create",
            ),
            path(
                "request-suggest/",
                view(views.request_suggest),
                name="clients_client_request_suggest",
            ),
            path(
                "request-search/",
                view(views.request_search),
                name="clients_client_request_search",
            ),
        ]
        return custom + urls

    # claude — segmented-type counts + current filter for the custom List.
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        base = Client.objects.all()
        extra_context["type_counts"] = {
            "all": base.count(),
            "person": base.filter(client_type=ClientType.PERSON).count(),
            "company": base.filter(client_type=ClientType.COMPANY).count(),
        }
        # The sidebar list_filter uses client_type__exact; mirror that param so
        # the segmented control highlights the active type.
        extra_context["current_client_type"] = (
            request.GET.get("client_type__exact")
            or request.GET.get("client_type")
            or ""
        )
        response = super().changelist_view(request, extra_context=extra_context)
        # Pre-compute the elided page range (template tags can't pass the
        # current page number to get_elided_page_range).
        try:
            cl = response.context_data["cl"]
            response.context_data["page_range"] = list(
                cl.paginator.get_elided_page_range(cl.page_num)
            )
            # Templates can't read leading-underscore annotations; expose aliases.
            for obj in cl.result_list:
                obj.request_count = obj._request_count
                obj.oferta_count = obj._oferta_count
                obj.zlecenie_count = obj._zlecenie_count
                obj.wniosek_count = obj._wniosek_count
        except (AttributeError, KeyError, TypeError):
            pass
        return response

    # claude — fully custom Detail (change_form). Renders the two-column
    # identity + linked-requests layout and binds the inline ClientForm. We
    # bypass the default change_view rendering but keep its permission gate.
    def change_view(self, request, object_id, form_url="", extra_context=None):
        if not self.has_change_permission(request):
            raise PermissionDenied

        client = get_object_or_404(Client, pk=object_id)
        can_edit = user_has_perm(request.user, "edit_clients")

        if request.method == "POST":
            if not can_edit:
                raise PermissionDenied
            form = ClientForm(request.POST, instance=client)
            if form.is_valid():
                form.save()
                messages.success(request, _("Client saved."))
                return redirect("admin:clients_client_change", client.pk)
        else:
            form = ClientForm(instance=client)

        summary = get_client_request_summary(client)

        # RequestMain owners come from the per-Req owners M2M; the child docs
        # show assigned_to. Cancelled/deleted RequestMain excluded to match the
        # summary count.
        main_qs = (
            client.requests
            .exclude(status__in=[RequestStatus.cancelled, RequestStatus.deleted])
            .prefetch_related("owners")
            .order_by("-created_at")
        )
        tabs = [
            {
                "key": "main", "label": "RequestMain", "count": summary["request_main"],
                "rows": build_request_rows(main_qs, "main", owners_attr="owners"),
                "filter_url": "admin:zetom_requestmain_changelist",
                "add_url": "admin:zetom_requestmain_add",
            },
            {
                "key": "oferta", "label": "Oferta", "count": summary["oferta"],
                "rows": build_request_rows(
                    client.ofertas.prefetch_related("assigned_to").order_by("-created_at"),
                    "oferta",
                ),
                "filter_url": "admin:zetom_oferta_changelist",
                "add_url": "admin:zetom_oferta_add",
            },
            {
                "key": "zlecenie", "label": "Zlecenie", "count": summary["zlecenie"],
                "rows": build_request_rows(
                    client.zlecenia.prefetch_related("assigned_to").order_by("-created_at"),
                    "zlecenie",
                ),
                "filter_url": "admin:zetom_zlecenie_changelist",
                "add_url": "admin:zetom_zlecenie_add",
            },
            {
                "key": "wniosek", "label": "Wniosek", "count": summary["wniosek"],
                "rows": build_request_rows(
                    client.wnioski.prefetch_related("assigned_to").order_by("-created_at"),
                    "wniosek",
                ),
                "filter_url": "admin:zetom_wniosek_changelist",
                "add_url": "admin:zetom_wniosek_add",
            },
        ]

        context = {
            **self.admin_site.each_context(request),
            "title": _("Client Detail"),
            "opts": self.model._meta,
            "client": client,
            "form": form,
            "summary": summary,
            "tabs": tabs,
            "total_requests": sum(t["count"] for t in tabs),
            "can_edit": can_edit,
            "has_view_permission": True,
            **(extra_context or {}),
        }
        return render(request, self.change_form_template, context)


# claude — контактные лица фирмы прямо в карточке Company (Osoby kontaktowe).
class CompanyPersonLinkInline(admin.TabularInline):
    model = CompanyPersonLink
    extra = 0
    fields = ("person", "position", "is_primary", "linked_by")
    autocomplete_fields = ("person",)
    readonly_fields = ("created_at",)


# claude — базовая регистрация фирмы (Klient/Firma). Кастомные List/Detail
# поверхности — Фаза 3. Права через те же RBAC-коды, что и ClientAdmin.
@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "nip", "type_supplier", "city", "phone", "email")
    search_fields = ("name", "short_name", "full_name", "nip")
    list_filter = ("type_supplier",)
    inlines = [CompanyPersonLinkInline]

    # claude — Фаза 3a: кастомная карточка фирмы (см. design_handoff_clients_unified §2).
    change_form_template = "admin/clients/company/change_form.html"

    # claude — Osoby kontaktowe add/edit/delete JSON endpoints (Task 2).
    # Same admin_view + RBAC pattern as ClientAdmin.get_urls above; the view
    # functions live in views.py alongside the other client-admin endpoints.
    def get_urls(self):
        urls = super().get_urls()
        view = self.admin_site.admin_view
        custom = [
            path(
                "<int:pk>/person/add/",
                view(views.company_person_add),
                name="clients_company_person_add",
            ),
            path(
                "<int:pk>/person/<int:link_pk>/edit/",
                view(views.company_person_edit),
                name="clients_company_person_edit",
            ),
            path(
                "<int:pk>/person/<int:link_pk>/delete/",
                view(views.company_person_delete),
                name="clients_company_person_delete",
            ),
        ]
        return custom + urls

    def has_module_permission(self, request):
        return user_has_perm(request.user, "view_clients")

    def has_view_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_clients")

    def has_add_permission(self, request):
        return user_has_perm(request.user, "edit_clients")

    def has_change_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_clients")

    def has_delete_permission(self, request, obj=None):
        return user_has_perm(request.user, "delete_clients")

    # claude — panel data-contract for the change_form template. Osoby/
    # zgloszenia/historia are wired for real (Task 3 polishes their visuals);
    # empty querysets render the `.empty` panel states from the handoff.
    def _build_company_context(self, request, company):
        can_edit = user_has_perm(request.user, "edit_clients")
        return {
            **self.admin_site.each_context(request),
            "title": _("Company Detail"),
            "opts": self.model._meta,
            "company": company,
            "can_edit": can_edit,
            "has_view_permission": True,
            "dane_podstawowe": {
                "nazwa": company.name,
                "nip": company.nip,
                "regon": company.regon,
                "typ_label": company.get_type_supplier_display(),
            },
            "dane_szczegolowe": {
                "kraj": company.country,
                "miasto": company.city,
                "wojewodztwo": company.voivodeship,
                "kod": company.post_code,
                "ulica": company.street,
                "email": company.email,
                "telefon": company.phone,
            },
            # claude — Osoby kontaktowe panel (Task 2). The table itself is
            # rendered client-side by Alpine (see the template's personPanel()),
            # so we hand it the same row shape the add/edit endpoints return
            # (views.company_person_row) as a JSON blob; `osoby` is kept only
            # to build `osoby_data` below (not read directly by the template).
            "osoby": (osoby := list(
                company.person_links.select_related("person").order_by(
                    "-is_primary", "person__last_name",
                )
            )),
            "osoby_data": [views.company_person_row(link) for link in osoby],
            # claude — Powiązane zgłoszenia (Task 3). Real RequestMain rows,
            # newest first; whole `.req` row links to the standard admin
            # change view (see change_form.html). Cancelled/deleted excluded,
            # matching ClientAdmin.change_view's main_qs.
            "zgloszenia": [
                {
                    "label": _zgloszenie_label(req),
                    "data": req.created_at,
                    "dept": _zgloszenie_dept_label(req.departments),
                    "status_label": req.get_status_display(),
                    "status_class": _ZGLOSZENIE_STATUS_CLASS.get(req.status, "zamkniete"),
                    "url": reverse("admin:zetom_requestmain_change", args=[req.pk]),
                }
                for req in RequestMain.objects.filter(company=company)
                .exclude(status__in=[RequestStatus.cancelled, RequestStatus.deleted])
                .order_by("-created_at")
            ],
            # claude — Historia kontaktów (Task 3), read-only. Interactions of
            # every person linked to this company (CompanyPersonLink), newest
            # first. No write endpoint — the template shows the readonly-note.
            "historia": [
                {
                    "data": interaction.contacted_at,
                    "kanal_label": interaction.get_channel_display(),
                    "sotrudnik": (
                        interaction.contacted_by.get_full_name()
                        or interaction.contacted_by.username
                    ) if interaction.contacted_by else "",
                    "kontakt_osoba": interaction.contact_person or interaction.client.full_name(),
                    "zaglowek": _zgloszenie_label(interaction.request) if interaction.request else "",
                    "summary": interaction.summary,
                }
                for interaction in (
                    ClientInteraction.objects
                    .filter(client__company_links__company=company)
                    .select_related("client", "contacted_by", "request")
                    .order_by("-contacted_at")
                )
            ],
        }

    # claude — fully custom Detail (change_form). Bypasses the default
    # change_view rendering (renders the id-hero + Dane panels layout from
    # the design handoff) but keeps the standard permission gate.
    def change_view(self, request, object_id, form_url="", extra_context=None):
        if not self.has_view_permission(request):
            raise PermissionDenied

        company = get_object_or_404(Company, pk=object_id)
        context = {
            **self._build_company_context(request, company),
            **(extra_context or {}),
        }
        return render(request, self.change_form_template, context)


# БАГ-9 + БАГ-10: отдельный раздел для просмотра всех контактов
@admin.register(ClientInteraction)
class ClientInteractionAdmin(admin.ModelAdmin):
    list_display = ("contacted_at", "client", "channel", "contact_person", "contacted_by", "request")
    list_filter = ("channel",)
    search_fields = ("client__first_name", "client__last_name", "client__company_name", "summary", "contact_person")
    autocomplete_fields = ("client", "request")
    readonly_fields = ("created_at",)
    date_hierarchy = "contacted_at"
