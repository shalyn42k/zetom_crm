from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from crm.status_manager.services.statuses import RequestStatus, Status
from crm.users.utils import user_has_perm
from crm.zetom.models import DepartmentsVariants, RequestMain

from . import views
from .models import (
    Client, ClientInteraction, Company, CompanyPersonLink, SupplierType,
)
from .services import build_request_rows, get_client_request_summary
from .services_contacts import (
    contact_rows_for_company, contact_rows_for_person,
    reminder_rows_for_company, reminder_rows_for_person,
)

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
    # claude — Phase 3b Task 1: Oferta/Zlecenie/Wniosek use the separate
    # Status enum (new/in_progress/waiting/done), not RequestStatus. Same
    # dict so the Person card's combined "Powiązane zgłoszenia" list can map
    # either enum's raw value straight to a badge class.
    Status.new: "oczekuje",
    Status.in_progress: "aktywne",
    Status.waiting: "oczekuje",
    Status.done: "zamkniete",
}

# claude — Phase 3b Task 1: human PL name per request type, used to build
# "<Typ> nr <pk> / <rok>" row titles on the Person card (no raw model names
# in UI, same rule as _zgloszenie_label above).
_PERSON_REQ_TYPE_LABEL = {
    "main": _("Zgłoszenie"),
    "oferta": _("Oferta"),
    "zlecenie": _("Zlecenie"),
    "wniosek": _("Wniosek"),
}

# claude — build_request_rows() only returns the raw status value (not its
# display label), and RequestMain/Oferta/Zlecenie/Wniosek pull from two
# different TextChoices (RequestStatus vs Status — no overlapping values),
# so one merged value→label dict covers every row the Person card builds.
_STATUS_DISPLAY = dict(RequestStatus.choices) | dict(Status.choices)


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


# claude — Phase 3b Task 1: id-hero avatar initials for the Person card.
# Prefers first_name/last_name (uppercased first letters); if both are
# blank, falls back to the first two characters of str(client) (e.g. a
# person recorded under a company-style display name); "?" if there's
# nothing at all to build initials from.
def _person_initials(client) -> str:
    first = (client.first_name or "").strip()
    last = (client.last_name or "").strip()
    if first or last:
        return (first[:1] + last[:1]).upper()
    fallback = str(client).strip()
    return fallback[:2].upper() if fallback else "?"


# claude — Phase 3b Task 1: combined "Powiązane zgłoszenia" rows for the
# Person card (RequestMain + Oferta + Zlecenie + Wniosek together, newest
# first). Reuses build_request_rows for the per-type query shaping (same
# querysets/prefetches the old change_view's tabs used) and just relabels
# each row for the flat list; get_client_request_summary still backs the
# panel's total count so it stays in sync with the four underlying counts.
def _person_zgloszenia_rows(client) -> list[dict]:
    sources = [
        (
            "main",
            client.requests
            .exclude(status__in=[RequestStatus.cancelled, RequestStatus.deleted])
            .prefetch_related("owners")
            .order_by("-created_at"),
            "owners", "admin:zetom_requestmain_change",
        ),
        (
            "oferta", client.ofertas.prefetch_related("assigned_to").order_by("-created_at"),
            "assigned_to", "admin:zetom_oferta_change",
        ),
        (
            "zlecenie", client.zlecenia.prefetch_related("assigned_to").order_by("-created_at"),
            "assigned_to", "admin:zetom_zlecenie_change",
        ),
        (
            "wniosek", client.wnioski.prefetch_related("assigned_to").order_by("-created_at"),
            "assigned_to", "admin:zetom_wniosek_change",
        ),
    ]
    rows = []
    for type_key, qs, owners_attr, change_name in sources:
        for row in build_request_rows(qs, type_key, owners_attr=owners_attr):
            rows.append({
                "label": _("%(type)s nr %(pk)s / %(year)s") % {
                    "type": _PERSON_REQ_TYPE_LABEL[type_key],
                    "pk": row["pk"], "year": row["date"].year,
                },
                "data": row["date"],
                "dept": row["dept"],
                "status_label": _STATUS_DISPLAY.get(row["status"], row["status"]),
                "status_class": _ZGLOSZENIE_STATUS_CLASS.get(row["status"], "zamkniete"),
                "url": row["change_url"],
            })
    rows.sort(key=lambda r: r["data"], reverse=True)
    return rows


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
    # claude — list_display/search_fields feed Django's default changelist
    # fallback only; the live list is the custom changelist_view below. Kept
    # off the dead company_name/client_type fields (Company data now lives on
    # Company via company_links; those columns drop in a later phase).
    list_display = (
        "first_name", "last_name", "email", "phone",
        "col_requests", "col_ofertas", "col_zlecenia", "col_wnioski",
    )
    search_fields = ("first_name", "last_name", "email", "phone")
    inlines = [ClientInteractionInline]
    # claude — Phase 3b Task 2: page size for the unified Klienci list
    # (changelist_view paginates a plain list, not list_display's QuerySet).
    list_per_page = 25

    # claude — custom List + Detail screens (see design_handoff_client_pages).
    # Phase 3b Task 1: Detail is the Person (Osoba) card from
    # design_handoff_clients_unified §3. Phase 3b Task 2: List is the unified
    # Klienci list (Company + private Client rows, see changelist_view below),
    # replacing the old client_type-segmented view. The old change_list.html /
    # change_form.html templates were removed once these took over.
    change_list_template = "admin/clients/client/klienci_list.html"
    # claude — the Person card is NOT change_form_template: Django renders that
    # same template from add_view too, and the card needs an existing object
    # (its {% url %} tags take client.pk), so setting it there made
    # /admin/clients/client/add/ die with NoReverseMatch. change_view below
    # renders this template explicitly; add stays on the stock admin form.
    person_card_template = "admin/clients/client/person_card.html"

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
            # claude — Add Client modal endpoints (see design_handoff_add_client).
            # create writes either a Company or a Client depending on `kind`;
            # suggest/search feed the optional "Powiąż zgłoszenie" picker and
            # narrow themselves to RequestMain when kind=firma.
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
            # claude — Dane osobowe save endpoint for the Person card
            # (mOsobowe modal, Phase 3b Task 1). RBAC edit_clients, enforced
            # again inside the view itself (views.person_save).
            path(
                "<int:pk>/person/save/",
                view(views.person_save),
                name="clients_client_person_save",
            ),
            # claude — Firmy panel on the Person card: search + attach an
            # existing Company, then edit (stanowisko/główny) or detach the
            # link. view_clients to search, edit_clients to write — re-checked
            # inside each view.
            path(
                "<int:pk>/company-search/",
                view(views.company_search),
                name="clients_client_company_search",
            ),
            path(
                "<int:pk>/attach-company/",
                view(views.attach_company),
                name="clients_client_attach_company",
            ),
            path(
                "<int:pk>/company-link/<int:link_pk>/save/",
                view(views.company_link_save),
                name="clients_client_company_link_save",
            ),
            path(
                "<int:pk>/company-link/<int:link_pk>/detach/",
                view(views.detach_company),
                name="clients_client_company_link_detach",
            ),
        ]
        return custom + urls

    # claude — Phase 3b Task 2: row builders for the unified Klienci list.
    # Company rows never touch Client.company_*/client_type (per the
    # normalization); private-person rows are Client objects with zero
    # company_links (contacts are excluded — they live under their Company's
    # Osoby kontaktowe panel, not in this top-level list).
    def _company_row(self, company):
        return {
            "kind": "company",
            "pk": company.pk,
            "nazwa": company.name,
            "nip": company.nip or "",
            "typ_value": company.type_supplier,
            "typ_label": company.get_type_supplier_display(),
            "telefon": company.phone,
            "email": company.email,
            "zgloszenia_count": company._zgloszenia_count,
            "url": reverse("admin:clients_company_change", args=[company.pk]),
        }

    def _person_row(self, client):
        # claude — люди, привязанные к фирме, больше не прячутся из списка,
        # поэтому «Osoba prywatna» перестало быть правдой для всех строк:
        # у контактного лица подписью идёт его фирма. company/company_url
        # нужны шаблону, чтобы дать ссылку прямо на карточку фирмы.
        company = client.primary_company()
        return {
            "kind": "person",
            "pk": client.pk,
            "nazwa": client.full_name() or _("Client #%(pk)s") % {"pk": client.pk},
            "nip": "",
            "typ_value": "",
            "typ_label": company.name if company else _("Osoba prywatna"),
            "company": company.name if company else "",
            "company_url": (
                reverse("admin:clients_company_change", args=[company.pk])
                if company else ""
            ),
            "telefon": client.phone,
            "email": client.email,
            # claude — the Person card counts all four document types
            # (get_client_request_summary), so the list column has to as well
            # or the same person shows two different numbers. Company rows stay
            # RequestMain-only because only RequestMain has a Company FK.
            "zgloszenia_count": (
                client._c_main + client._c_oferta + client._c_zlecenie + client._c_wniosek
            ),
            "url": reverse("admin:clients_client_change", args=[client.pk]),
        }

    # claude — Phase 3b Task 2: unified "Klienci" list = Company rows +
    # private-person rows (Client with no company_links) merged into one
    # table. Fully custom (no ModelAdmin ChangeList machinery — same pattern
    # as change_view above) because the merged result is a plain Python
    # list, not a QuerySet, and the two very different row shapes need
    # normalizing before they can share one Paginator/table. Filters
    # (?rodzaj=firmy|osoby, ?typ=<supplier>, ?q=<search>) are applied at
    # build time, before pagination.
    def changelist_view(self, request, extra_context=None):
        if not self.has_view_permission(request):
            raise PermissionDenied

        rodzaj = request.GET.get("rodzaj", "")
        typ = request.GET.get("typ", "")
        q = request.GET.get("q", "").strip()
        typ_active = typ and typ != "all"

        excluded_statuses = [RequestStatus.cancelled, RequestStatus.deleted]

        # claude — annotate() (not a per-row query) keeps this N+1-free: one
        # extra join per queryset, not one query per row. Four separate
        # distinct counts rather than one summed expression — joining four M2Ms
        # in a single aggregate multiplies rows and inflates every count.
        companies = Company.objects.annotate(
            _zgloszenia_count=Count(
                "requests",
                filter=~Q(requests__status__in=excluded_statuses),
                distinct=True,
            ),
        )
        if typ_active:
            companies = companies.filter(type_supplier=typ)
        if q:
            companies = companies.filter(Q(name__icontains=q) | Q(nip__icontains=q))

        # claude — раньше здесь стоял `.filter(company_links__isnull=True)`:
        # человек, привязанный к фирме, полностью пропадал из Klienci и его
        # можно было найти только зайдя внутрь карточки фирмы. Теперь в
        # списке видны все люди; принадлежность к фирме не прячет строку, а
        # показывается подписью под именем (см. _person_row).
        # prefetch — модель прямо предупреждает (Client.primary_company), что
        # без него на каждую строку уходит отдельный запрос.
        persons = Client.objects.prefetch_related("company_links__company").annotate(
            _c_main=Count(
                "requests",
                filter=~Q(requests__status__in=excluded_statuses),
                distinct=True,
            ),
            _c_oferta=Count("ofertas", distinct=True),
            _c_zlecenie=Count("zlecenia", distinct=True),
            _c_wniosek=Count("wnioski", distinct=True),
        )
        if typ_active:
            # claude — Typ dostawcy only exists on Company; a person can
            # never match a supplier type, so selecting one zeroes this side.
            persons = persons.none()
        if q:
            # claude — по названию фирмы тоже: контактное лицо теперь в списке,
            # и искать его по работодателю — первое, что приходит в голову.
            persons = persons.filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(company_links__company__name__icontains=q)
            ).distinct()

        # claude — sort/paginate on identity tuples, not on built rows. Two
        # models can't share a QuerySet, so the merge has to happen in Python;
        # pulling just (pk, name) keeps that to a couple of scalar columns
        # instead of materializing every Company and Client on every page view.
        company_keys = list(companies.values_list("pk", "name"))
        person_keys = list(persons.values_list("pk", "first_name", "last_name"))

        counts = {
            "all": len(company_keys) + len(person_keys),
            "firmy": len(company_keys),
            "osoby": len(person_keys),
        }

        # claude — one global alphabetical order across both kinds. Sorting
        # each side separately and concatenating buried every private person
        # behind every company, so on a 200-company base page 1 was all firms.
        keys = []
        if rodzaj != "osoby":
            keys += [((name or "").lower(), "company", pk) for pk, name in company_keys]
        if rodzaj != "firmy":
            keys += [
                (" ".join(filter(None, (first, last))).lower(), "person", pk)
                for pk, first, last in person_keys
            ]
        keys.sort()

        paginator = Paginator(keys, self.list_per_page)
        page_obj = paginator.get_page(request.GET.get("page"))

        # claude — only now, for the ≤list_per_page keys on this page, fetch the
        # objects (with their count annotations) and build display rows.
        page_keys = list(page_obj)
        company_pks = [pk for _k, kind, pk in page_keys if kind == "company"]
        person_pks = [pk for _k, kind, pk in page_keys if kind == "person"]
        companies_by_pk = {c.pk: c for c in companies.filter(pk__in=company_pks)}
        persons_by_pk = {p.pk: p for p in persons.filter(pk__in=person_pks)}
        rows = [
            self._company_row(companies_by_pk[pk]) if kind == "company"
            else self._person_row(persons_by_pk[pk])
            for _k, kind, pk in page_keys
        ]

        context = {
            **self.admin_site.each_context(request),
            "title": _("Clients"),
            # claude — deliberately NOT passing `opts`: Unfold's header_title
            # builds the "Clients › Companies › …" chain from it, and those
            # links point at the stock changelists these designed pages
            # replaced. Each page carries its own header and "Wróć".
            "has_add_permission": self.has_add_permission(request),
            "counts": counts,
            "current_rodzaj": rodzaj,
            "current_typ": typ,
            "current_q": q,
            "supplier_types": SupplierType.choices,
            "rows": rows,
            "page_obj": page_obj,
            "paginator": paginator,
            "page_range": list(paginator.get_elided_page_range(page_obj.number)),
            **(extra_context or {}),
        }
        return TemplateResponse(request, self.change_list_template, context)

    # claude — Phase 3b Task 1: panel data-contract for the Person (Osoba)
    # card. Firmy comes only from company_links (never Client.company_*, per
    # the normalization — a Person can sit in N companies via
    # CompanyPersonLink). Zgłoszenia/historia mirror CompanyAdmin's
    # _build_company_context so both cards share one visual language.
    def _build_person_context(self, request, client):
        can_edit = user_has_perm(request.user, "edit_clients")
        # client.company_links is prefetched by change_view (see below);
        # list(...) reads the prefetch cache — calling .first() here instead
        # would silently re-query and defeat that prefetch.
        links = sorted(
            list(client.company_links.all()),
            key=lambda link: (not link.is_primary, link.company.name),
        )
        # claude — summary's counts (request_main/oferta/zlecenie/wniosek)
        # sum to exactly len(zgloszenia) below; kept as the panel's header
        # count so it comes from the same shared service as the old tabs did.
        summary = get_client_request_summary(client)
        return {
            **self.admin_site.each_context(request),
            "title": _("Person Detail"),
            # claude — deliberately NOT passing `opts`: Unfold's header_title
            # builds the "Clients › Companies › …" chain from it, and those
            # links point at the stock changelists these designed pages
            # replaced. Each page carries its own header and "Wróć".
            "client": client,
            "can_edit": can_edit,
            "has_view_permission": True,
            # claude — id-hero avatar initials: first_name[0]+last_name[0]
            # uppercased; falls back to str(client)'s first two chars, then
            # "?" if there's nothing at all to build initials from.
            "person_initials": _person_initials(client),
            # claude — Dane osobowe panel + mOsobowe modal seed. Never reads
            # Client.company_name/company_nip/client_type — only the
            # person's own identity fields.
            "dane_osobowe": {
                "imie": client.first_name or "",
                "nazwisko": client.last_name or "",
                "telefon": client.phone.as_international if client.phone else "",
                "email": client.email or "",
            },
            "firmy": [
                {
                    # claude — link_pk drives the panel's edit/detach buttons
                    # (clients_client_company_link_save / _detach); those act on
                    # the CompanyPersonLink, never on the Company itself.
                    "link_pk": link.pk,
                    "nazwa": link.company.name,
                    "stanowisko": link.position,
                    "is_primary": link.is_primary,
                    "url": reverse("admin:clients_company_change", args=[link.company_id]),
                }
                for link in links
            ],
            # claude — Powiązane zgłoszenia: combined RequestMain/Oferta/
            # Zlecenie/Wniosek list (see _person_zgloszenia_rows above).
            "zgloszenia": _person_zgloszenia_rows(client),
            "total_requests": sum(summary.values()),
            # claude — Historia kontaktów (read-only), same row shape as
            # CompanyAdmin._build_company_context's historia (README §3:
            # "Historia kontaktów (read-only, как выше)" — reuse as-is).
            # Task 7: now reads zetom.StepNote (contact notes + closed
            # reminders) instead of clients.ClientInteraction — see
            # services_contacts.py.
            "historia": contact_rows_for_person(client),
            # claude — Task 7: open reminders ("Zaplanowane"), sorted by
            # next_contact_at ascending.
            "zaplanowane": reminder_rows_for_person(client),
        }

    # claude — fully custom Detail (change_form). Renders the Person (Osoba)
    # card (Dane osobowe + Firmy + Powiązane zgłoszenia + Historia kontaktów).
    # Bypasses the default change_view rendering but keeps the permission gate.
    # claude — gate is view_clients, not edit_clients: the card is a read
    # surface (every write control is behind its own can_edit check), and
    # requiring edit here locked read-only users out of it while the Company
    # card next door let them in.
    def change_view(self, request, object_id, form_url="", extra_context=None):
        if not self.has_view_permission(request):
            raise PermissionDenied

        client = get_object_or_404(
            Client.objects.prefetch_related("company_links__company"),
            pk=object_id,
        )
        context = {
            **self._build_person_context(request, client),
            **(extra_context or {}),
        }
        return render(request, self.person_card_template, context)


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
    # claude — same trap as ClientAdmin.person_card_template, plus one more:
    # even with change_form_template unset, Django's add_view falls back to
    # "admin/<app>/<model>/change_form.html" by convention — which is exactly
    # where this card used to live, so add_view kept picking it up and dying on
    # {% url ... company.pk %}. Hence the deliberately off-convention filename.
    company_card_template = "admin/clients/company/company_card.html"

    # claude — Osoby kontaktowe add/edit/delete + Dane podstawowe/szczegółowe
    # save JSON endpoints. Same admin_view + RBAC pattern as ClientAdmin.
    # get_urls above; the view functions live in views.py alongside the other
    # client-admin endpoints.
    def get_urls(self):
        urls = super().get_urls()
        view = self.admin_site.admin_view
        custom = [
            # claude — the only write path for the Company's own fields:
            # change_view renders a custom template and never builds a
            # ModelForm, so the card's "Edytuj" buttons post here.
            path(
                "<int:pk>/save/",
                view(views.company_save),
                name="clients_company_save",
            ),
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
            # claude — deliberately NOT passing `opts`: Unfold's header_title
            # builds the "Clients › Companies › …" chain from it, and those
            # links point at the stock changelists these designed pages
            # replaced. Each page carries its own header and "Wróć".
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
            # claude — seeds for the two "Edytuj" modals. Keys are the model
            # field names on purpose: the modal posts them straight through and
            # views._COMPANY_SECTIONS reads them by the same names, so there is
            # no PL↔model translation layer to keep in sync.
            "dane_podstawowe_form": {
                "name": company.name,
                "nip": company.nip or "",
                "regon": company.regon,
                "type_supplier": company.type_supplier,
            },
            "dane_szczegolowe_form": {
                "country": company.country,
                "city": company.city,
                "voivodeship": company.voivodeship,
                "post_code": company.post_code,
                "street": company.street,
                "email": company.email,
                "phone": company.phone.as_international if company.phone else "",
            },
            "supplier_types": SupplierType.choices,
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
            # claude — Historia kontaktów (Task 3), read-only. Notes of every
            # person linked to this company (CompanyPersonLink), newest
            # first. No write endpoint — the template shows the readonly-note.
            # Task 7: now reads zetom.StepNote (contact notes + closed
            # reminders) instead of clients.ClientInteraction — see
            # services_contacts.py.
            "historia": contact_rows_for_company(company),
            # claude — Task 7: open reminders ("Zaplanowane") of every person
            # linked to this company, sorted by next_contact_at ascending.
            "zaplanowane": reminder_rows_for_company(company),
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
        return render(request, self.company_card_template, context)


# БАГ-9 + БАГ-10: отдельный раздел для просмотра всех контактов
@admin.register(ClientInteraction)
class ClientInteractionAdmin(admin.ModelAdmin):
    list_display = ("contacted_at", "client", "channel", "contact_person", "contacted_by", "request")
    list_filter = ("channel",)
    # claude — client__company_name died with migration 0009 (company data moved
    # to Company), so any search here raised FieldError. Company name is now
    # reached through the CompanyPersonLink M2M; Django adds the needed
    # distinct() itself when a search path spans a to-many relation.
    search_fields = (
        "client__first_name", "client__last_name",
        "client__company_links__company__name", "summary", "contact_person",
    )
    autocomplete_fields = ("client", "request")
    readonly_fields = ("created_at",)
    date_hierarchy = "contacted_at"
