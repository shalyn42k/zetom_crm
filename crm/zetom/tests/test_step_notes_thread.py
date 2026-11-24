from datetime import timedelta
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from crm.clients.models import Client, Company, CompanyPersonLink
from crm.zetom.admin.children import OfertaAdmin
from crm.zetom.admin.requestmain import RequestMainAdmin
from crm.zetom.models import Oferta, RequestClientLink, RequestMain, StepNote

# claude — ManifestStaticFilesStorage requires collectstatic to resolve
# {% static %} lookups (including the ones the admin Media class makes);
# tests render the change form without running collectstatic first, so
# swap in a storage that serves straight from STATICFILES_DIRS. Same
# pattern as test_dupe_render_smoke.py / test_client_link_admin.py.
_SIMPLE_STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


class StepNotesThreadTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("admin", "admin@example.com", "pass12345")
        self.main = RequestMain.objects.create(
            first_name="Jan",
            last_name="Kowalski",
            phone="+48500100200",
            email="jan@example.com",
            company_name="Zetom",
        )
        self.oferta = Oferta.objects.create(
            from_main=self.main,
            first_name="Jan",
            last_name="Kowalski",
            phone="+48500100200",
            email="jan@example.com",
            company_name="Zetom",
        )

        self.main_admin = RequestMainAdmin(RequestMain, admin.site)
        self.oferta_admin = OfertaAdmin(Oferta, admin.site)

    def test_requestmain_context_includes_notes_from_child_documents(self):
        StepNote.objects.create(
            author=self.user,
            target=self.main,
            action="Main action",
            text="Main note",
            contacted_at=timezone.now(),
        )
        StepNote.objects.create(
            author=self.user,
            target=self.oferta,
            action="Offer action",
            text="Offer note",
            contacted_at=timezone.now(),
        )

        context = self.main_admin._build_step_notes_context(self.main)
        notes_texts = [note.text for note in context["step_notes"]]

        self.assertIn("Main note", notes_texts)
        self.assertIn("Offer note", notes_texts)

    def test_child_context_includes_notes_from_request_thread(self):
        StepNote.objects.create(
            author=self.user,
            target=self.main,
            action="Main action",
            text="Main thread note",
            contacted_at=timezone.now(),
        )
        StepNote.objects.create(
            author=self.user,
            target=self.oferta,
            action="Offer action",
            text="Offer thread note",
            contacted_at=timezone.now(),
        )

        context = self.oferta_admin._build_step_notes_context(self.oferta)
        notes_texts = [note.text for note in context["step_notes"]]

        self.assertIn("Main thread note", notes_texts)
        self.assertIn("Offer thread note", notes_texts)


# claude — Task 12: step_notes_persons (request clients + company persons,
# deduplicated) and the cc-* kind toggle markup in the shared modal.
class StepNoteModalTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            "admin2", "admin2@example.com", "pass12345",
        )
        self.main = RequestMain.objects.create(
            first_name="Jan",
            last_name="Kowalski",
            phone="+48500100200",
            email="jan@example.com",
            company_name="Zetom",
        )
        self.main_admin = RequestMainAdmin(RequestMain, admin.site)

    def test_modal_context_lists_request_persons(self):
        company = Company.objects.create(name="Zetom Sp. z o.o.", nip="1234563218")
        self.main.company = company
        self.main.save(update_fields=["company"])

        request_person = Client.objects.create(first_name="Anna", last_name="Nowak")
        RequestClientLink.objects.create(request=self.main, client=request_person)

        company_person = Client.objects.create(first_name="Piotr", last_name="Zielinski")
        CompanyPersonLink.objects.create(company=company, person=company_person)

        # claude — linked both ways (request AND company) must appear once.
        both_person = Client.objects.create(first_name="Ewa", last_name="Wojcik")
        RequestClientLink.objects.create(request=self.main, client=both_person)
        CompanyPersonLink.objects.create(company=company, person=both_person)

        context = self.main_admin._build_step_notes_context(self.main)
        persons = context["step_notes_persons"]

        self.assertEqual(
            {person.pk for person in persons},
            {request_person.pk, company_person.pk, both_person.pk},
        )
        self.assertEqual(len(persons), 3)

    def test_modal_context_excludes_unrelated_persons(self):
        unrelated = Client.objects.create(first_name="Obcy", last_name="Klient")

        context = self.main_admin._build_step_notes_context(self.main)

        self.assertNotIn(unrelated, context["step_notes_persons"])

    # claude — Fix round (coordinator review): the original version of this
    # test only checked the two toggle-branch descriptions, which would
    # still pass with the .cc-stage wrapper missing (unstyled modal), wrong
    # field `name`s (silent data loss on submit), or a broken :disabled
    # binding (cross-branch field clobbering — see the template's own
    # comment on why that binding exists). Broadened to actually hold the
    # modal to its contract.
    @override_settings(STORAGES=_SIMPLE_STATIC)
    def test_modal_renders_kind_toggle(self):
        now = timezone.now()
        StepNote.objects.create(
            author=self.user,
            target=self.main,
            kind=StepNote.Kind.REMINDER,
            text="Overdue reminder",
            next_contact_at=now - timedelta(days=1),
        )
        StepNote.objects.create(
            author=self.user,
            target=self.main,
            kind=StepNote.Kind.REMINDER,
            text="Upcoming reminder",
            next_contact_at=now + timedelta(days=1),
        )

        self.client.force_login(self.user)
        url = reverse("admin:zetom_requestmain_change", args=[self.main.pk])

        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

        # claude — every cc-* rule in company_card.css is scoped under
        # .cc-stage; without the wrapper the whole modal renders unstyled.
        self.assertContains(resp, 'class="cc-stage"')

        # claude — StepNoteCreateForm's eight fields must all reach the DOM
        # under their exact names, or create_step_note() silently never
        # sees the submitted value for that field.
        for field_name in (
            "kind", "action", "text", "channel",
            "contacted_at", "next_contact_at", "person", "contact_person",
        ):
            self.assertContains(resp, f'name="{field_name}"')

        # claude — both toggle branches, plus the :disabled binding that
        # keeps the inactive branch's same-named inputs from clobbering
        # the active branch's values on submit.
        self.assertContains(resp, "Log a conversation that already happened")
        self.assertContains(resp, "Plan a future contact")
        self.assertContains(resp, ':disabled="kind !== \'contact\'"')
        self.assertContains(resp, ':disabled="kind !== \'reminder\'"')

        # claude — overdue modifier: present once (the past reminder),
        # absent for the future one.
        self.assertContains(resp, "hev overdue", count=1)

        # claude — no inline "add person" control (explicit brief
        # requirement): the only clients-app link in the modal must be the
        # changelist (browse/manage), never the add view.
        self.assertContains(resp, reverse("admin:clients_client_changelist"))
        self.assertNotContains(resp, reverse("admin:clients_client_add"))


# claude — Fix-round: the document card's modal sorted and rendered
# `created_at`. Every note migrated from ClientInteraction therefore read
# "X minutes ago" (the migration's run time), and a note logged today about
# last week's call read as "now". The clients-side panels already compensate
# with Coalesce("contacted_at", "created_at") — see
# crm/clients/services_contacts.py::_history_notes — so both surfaces have
# to agree on the same timestamp.
@override_settings(STORAGES=_SIMPLE_STATIC)
class StepNoteTimelineTimestampTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            "admin3", "admin3@example.com", "pass12345",
        )
        self.main = RequestMain.objects.create(
            first_name="Jan",
            last_name="Kowalski",
            phone="+48500100200",
            email="jan@example.com",
            company_name="Zetom",
        )
        self.main_admin = RequestMainAdmin(RequestMain, admin.site)

    def test_timeline_is_ordered_by_when_the_contact_happened(self):
        now = timezone.now()
        # written first, but about a conversation that happened *today*
        recent = StepNote.objects.create(
            author=self.user, target=self.main, text="Rozmowa dzisiaj",
            contacted_at=now,
        )
        # written second, backfilling a conversation from last week
        old = StepNote.objects.create(
            author=self.user, target=self.main, text="Rozmowa w zeszłym tygodniu",
            contacted_at=now - timedelta(days=7),
        )

        notes = self.main_admin._build_step_notes_context(self.main)["step_notes"]

        self.assertEqual([note.pk for note in notes], [recent.pk, old.pk])

    def test_timeline_renders_contacted_at_not_created_at(self):
        contacted = timezone.now() - timedelta(days=7)
        StepNote.objects.create(
            author=self.user, target=self.main, text="Rozmowa w zeszłym tygodniu",
            contacted_at=contacted,
        )

        self.client.force_login(self.user)
        resp = self.client.get(reverse("admin:zetom_requestmain_change", args=[self.main.pk]))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(
            resp, timezone.localtime(contacted).strftime("%Y-%m-%d %H:%M"),
        )

    def test_timeline_falls_back_to_created_at(self):
        # a closed reminder never had a conversation, so it has no
        # contacted_at — Coalesce must fall back rather than sort it to NULL.
        note = StepNote.objects.create(
            author=self.user, target=self.main, kind=StepNote.Kind.REMINDER,
            text="Zamknięte przypomnienie",
            next_contact_at=timezone.now() - timedelta(days=1),
            done_at=timezone.now(),
        )

        notes = self.main_admin._build_step_notes_context(self.main)["step_notes"]

        self.assertEqual([n.pk for n in notes], [note.pk])
        self.assertEqual(notes[0].sort_at, note.created_at)


# claude — Fix-round, spec §5.2/§9: a reminder created from a DOCUMENT card
# has no `person` (the modal disables that select in reminder mode), so it
# matched neither "Zaplanowane" panel — both filter on `person` — and the only
# "done" endpoint required person=client. Such reminders were unclosable and
# stayed overdue forever, breaking the DoD line "напоминание можно поставить и
# закрыть с карточки персоны и с карточки документа". These pin the missing
# half: an open reminder is listed separately on the document card and closed
# through zetom's own done endpoint.
@override_settings(STORAGES=_SIMPLE_STATIC)
class DocumentCardReminderTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            "admin4", "admin4@example.com", "pass12345",
        )
        self.client.force_login(self.user)
        self.main = RequestMain.objects.create(
            first_name="Jan", last_name="Kowalski",
            phone="+48500100200", email="jan@example.com", company_name="Zetom",
        )
        self.oferta = Oferta.objects.create(
            from_main=self.main,
            first_name="Jan", last_name="Kowalski",
            phone="+48500100200", email="jan@example.com", company_name="Zetom",
        )
        self.main_admin = RequestMainAdmin(RequestMain, admin.site)

    def _reminder(self, target=None, done_at=None, **kwargs):
        return StepNote.objects.create(
            author=self.user,
            target=target if target is not None else self.main,
            kind=StepNote.Kind.REMINDER,
            person=None,
            next_contact_at=timezone.now() + timedelta(days=1),
            done_at=done_at,
            **kwargs,
        )

    def test_open_reminder_without_person_is_listed_on_the_document_card(self):
        note = self._reminder(text="Wysłać ofertę w poniedziałek")

        context = self.main_admin._build_step_notes_context(self.main)

        self.assertEqual(
            [n.pk for n in context["step_notes_open_reminders"]], [note.pk],
        )
        # an open reminder is not history — same split as the client cards
        self.assertNotIn(note.pk, [n.pk for n in context["step_notes"]])

    def test_closed_reminder_moves_from_the_panel_into_history(self):
        note = self._reminder(text="Zamknięte", done_at=timezone.now())

        context = self.main_admin._build_step_notes_context(self.main)

        self.assertEqual(context["step_notes_open_reminders"], [])
        self.assertIn(note.pk, [n.pk for n in context["step_notes"]])

    def test_reminder_of_a_child_document_shows_on_the_parent_card(self):
        note = self._reminder(target=self.oferta, text="Przypomnienie oferty")

        context = self.main_admin._build_step_notes_context(self.main)

        self.assertEqual(
            [n.pk for n in context["step_notes_open_reminders"]], [note.pk],
        )

    def test_document_card_renders_the_open_reminder_and_its_close_button(self):
        note = self._reminder(text="Wysłać ofertę w poniedziałek")
        done_url = reverse(
            "admin:zetom_requestmain_step_note_done", args=[self.main.pk, note.pk],
        )

        resp = self.client.get(reverse("admin:zetom_requestmain_change", args=[self.main.pk]))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Wysłać ofertę w poniedziałek")
        self.assertContains(resp, done_url)

    def test_done_endpoint_closes_a_reminder_without_a_person(self):
        note = self._reminder()
        done_url = reverse(
            "admin:zetom_requestmain_step_note_done", args=[self.main.pk, note.pk],
        )

        resp = self.client.post(done_url)

        self.assertEqual(resp.status_code, 302)
        note.refresh_from_db()
        self.assertIsNotNone(note.done_at)

    def test_done_endpoint_closes_a_child_documents_reminder_from_its_own_card(self):
        note = self._reminder(target=self.oferta)
        done_url = reverse(
            "admin:zetom_oferta_step_note_done", args=[self.oferta.pk, note.pk],
        )

        resp = self.client.post(done_url)

        self.assertEqual(resp.status_code, 302)
        note.refresh_from_db()
        self.assertIsNotNone(note.done_at)

    def test_done_endpoint_rejects_a_note_from_another_thread(self):
        other_main = RequestMain.objects.create(
            first_name="Anna", last_name="Nowak",
            phone="+48500100201", email="anna@example.com",
        )
        note = self._reminder(target=other_main)
        done_url = reverse(
            "admin:zetom_requestmain_step_note_done", args=[self.main.pk, note.pk],
        )

        resp = self.client.post(done_url)

        self.assertEqual(resp.status_code, 403)
        note.refresh_from_db()
        self.assertIsNone(note.done_at)

    def test_done_endpoint_rejects_a_contact_note(self):
        note = StepNote.objects.create(
            author=self.user, target=self.main, text="Rozmowa",
            contacted_at=timezone.now(),
        )
        done_url = reverse(
            "admin:zetom_requestmain_step_note_done", args=[self.main.pk, note.pk],
        )

        resp = self.client.post(done_url)

        self.assertEqual(resp.status_code, 302)
        note.refresh_from_db()
        self.assertIsNone(note.done_at)

    def test_get_does_not_close_a_reminder(self):
        note = self._reminder()
        done_url = reverse(
            "admin:zetom_requestmain_step_note_done", args=[self.main.pk, note.pk],
        )

        resp = self.client.get(done_url)

        self.assertEqual(resp.status_code, 302)
        note.refresh_from_db()
        self.assertIsNone(note.done_at)

    @patch("crm.zetom.admin.base.user_has_perm")
    def test_done_endpoint_requires_edit_permission(self, perm_mock):
        # same gate as creating a note on this surface (spec §5.2)
        perm_mock.side_effect = lambda user, perm: perm != "edit_requests"
        note = self._reminder()
        done_url = reverse(
            "admin:zetom_requestmain_step_note_done", args=[self.main.pk, note.pk],
        )

        resp = self.client.post(done_url)

        self.assertEqual(resp.status_code, 403)
        note.refresh_from_db()
        self.assertIsNone(note.done_at)
