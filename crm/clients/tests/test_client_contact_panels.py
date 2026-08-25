# claude
"""Task 7: contact-history and reminders row-builders that read StepNote
instead of ClientInteraction.

Task 9 (below) adds the write side: log-a-contact / close-a-reminder
endpoints on ClientAdmin, plus the step-notes-modal context keys both
cards must expose.

See .superpowers/sdd/2026-08-24-step-notes-unification/task-7-brief.md and
task-9-brief.md.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from crm.clients.models import Client, Company, CompanyPersonLink
from crm.clients.services_contacts import (
    contact_rows_for_company, contact_rows_for_person,
    reminder_rows_for_company, reminder_rows_for_person,
)
from crm.users.models import Permission
from crm.zetom.models import (
    Oferta, RequestClientLink, RequestMain, StepNote, Wniosek, Zlecenie,
)
from crm.zetom.services.step_notes import create_step_note

BASE_REQ = {
    "phone": "+48501600300",
    "email": "jan@zetom.pl",
}


class PersonHistoryTest(TestCase):
    def setUp(self):
        self.person = Client.objects.create(first_name="Jan", last_name="Kowalski")

    def test_person_history_shows_own_contact_notes(self):
        request_main = RequestMain.objects.create(**BASE_REQ)
        create_step_note(
            author=None,
            kind=StepNote.Kind.CONTACT,
            text="Rozmowa o ofercie",
            person=self.person,
            channel=StepNote.Channel.CALL,
            contact_person="Jan Kowalski",
            contacted_at=timezone.now(),
            target=request_main,
        )

        rows = contact_rows_for_person(self.person)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["summary"], "Rozmowa o ofercie")
        self.assertEqual(row["kontakt_osoba"], "Jan Kowalski")
        self.assertIn(str(request_main.pk), row["zaglowek"])

    def test_person_history_excludes_reminders(self):
        create_step_note(
            author=None,
            kind=StepNote.Kind.REMINDER,
            person=self.person,
            next_contact_at=timezone.now() + timedelta(days=1),
        )

        rows = contact_rows_for_person(self.person)

        self.assertEqual(rows, [])

    def test_closed_reminder_appears_in_history(self):
        note = create_step_note(
            author=None,
            kind=StepNote.Kind.REMINDER,
            text="Oddzwonić w sprawie kalibracji",
            person=self.person,
            next_contact_at=timezone.now() - timedelta(days=1),
        )
        note.done_at = timezone.now()
        note.save(update_fields=["done_at"])

        rows = contact_rows_for_person(self.person)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["summary"], "Oddzwonić w sprawie kalibracji")


class CompanyHistoryTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Zetom Sp. z o.o.", nip="1234563218")
        self.other_company = Company.objects.create(name="Other Sp.")
        self.person = Client.objects.create(first_name="Jan", last_name="Kowalski")
        self.other_person = Client.objects.create(first_name="Anna")
        CompanyPersonLink.objects.create(company=self.company, person=self.person)
        CompanyPersonLink.objects.create(company=self.other_company, person=self.other_person)

    def test_company_history_includes_notes_of_all_its_persons(self):
        second_person = Client.objects.create(first_name="Piotr", last_name="Nowak")
        CompanyPersonLink.objects.create(company=self.company, person=second_person)
        create_step_note(
            author=None, kind=StepNote.Kind.CONTACT, text="Pierwszy kontakt",
            person=self.person, contacted_at=timezone.now(),
        )
        create_step_note(
            author=None, kind=StepNote.Kind.CONTACT, text="Drugi kontakt",
            person=second_person, contacted_at=timezone.now(),
        )

        rows = contact_rows_for_company(self.company)

        self.assertEqual(
            {row["summary"] for row in rows},
            {"Pierwszy kontakt", "Drugi kontakt"},
        )

    def test_company_history_excludes_notes_of_other_company_persons(self):
        # Regression guard, same isolation check as
        # test_company_card_panels.py::test_unrelated_company_history_not_leaked.
        create_step_note(
            author=None, kind=StepNote.Kind.CONTACT,
            text="Nie powinno się tu pojawić",
            person=self.other_person, contacted_at=timezone.now(),
        )

        rows = contact_rows_for_company(self.company)

        self.assertEqual(rows, [])

    def test_company_reminders_include_only_this_companys_open_reminders(self):
        create_step_note(
            author=None, kind=StepNote.Kind.REMINDER, text="Oddzwonić",
            person=self.person, next_contact_at=timezone.now() + timedelta(days=1),
        )
        create_step_note(
            author=None, kind=StepNote.Kind.REMINDER, text="Nie nasze",
            person=self.other_person, next_contact_at=timezone.now() + timedelta(days=1),
        )

        rows = reminder_rows_for_company(self.company)

        self.assertEqual([row["summary"] for row in rows], ["Oddzwonić"])

    # claude — Task 13: the company card's "Zaplanowane" checkmark posts to
    # clients_client_step_note_done, which is addressed by the owning
    # PERSON's pk (see task-9-brief.md), not the company's. A company can
    # have reminders from several different persons on the same panel, so
    # each row must carry its own person pk to build the right URL — reusing
    # one person's pk for every row would let the checkmark 403 (wrong
    # person) or, worse, close the wrong person's reminder.
    def test_company_reminder_rows_carry_each_reminders_owning_person_pk(self):
        second_person = Client.objects.create(first_name="Piotr", last_name="Nowak")
        CompanyPersonLink.objects.create(company=self.company, person=second_person)
        create_step_note(
            author=None, kind=StepNote.Kind.REMINDER, text="Oddzwonić do Jana",
            person=self.person, next_contact_at=timezone.now() + timedelta(days=1),
        )
        create_step_note(
            author=None, kind=StepNote.Kind.REMINDER, text="Oddzwonić do Piotra",
            person=second_person, next_contact_at=timezone.now() + timedelta(days=1),
        )

        rows = reminder_rows_for_company(self.company)

        by_summary = {row["summary"]: row["person_pk"] for row in rows}
        self.assertEqual(by_summary["Oddzwonić do Jana"], self.person.pk)
        self.assertEqual(by_summary["Oddzwonić do Piotra"], second_person.pk)


class ReminderPanelTest(TestCase):
    def setUp(self):
        self.person = Client.objects.create(first_name="Jan", last_name="Kowalski")

    def test_reminders_panel_lists_only_open_reminders(self):
        open_note = create_step_note(
            author=None, kind=StepNote.Kind.REMINDER, text="Otwarte",
            person=self.person, next_contact_at=timezone.now() + timedelta(days=1),
        )
        closed_note = create_step_note(
            author=None, kind=StepNote.Kind.REMINDER, text="Zamknięte",
            person=self.person, next_contact_at=timezone.now() + timedelta(days=1),
        )
        closed_note.done_at = timezone.now()
        closed_note.save(update_fields=["done_at"])

        rows = reminder_rows_for_person(self.person)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["note_pk"], open_note.pk)
        self.assertEqual(rows[0]["person_pk"], self.person.pk)

    def test_overdue_reminder_is_flagged(self):
        create_step_note(
            author=None, kind=StepNote.Kind.REMINDER, text="Przeterminowane",
            person=self.person, next_contact_at=timezone.now() - timedelta(days=1),
        )
        create_step_note(
            author=None, kind=StepNote.Kind.REMINDER, text="Przyszłe",
            person=self.person, next_contact_at=timezone.now() + timedelta(days=1),
        )

        rows = reminder_rows_for_person(self.person)
        by_summary = {row["summary"]: row for row in rows}

        self.assertTrue(by_summary["Przeterminowane"]["is_overdue"])
        self.assertFalse(by_summary["Przyszłe"]["is_overdue"])


class TargetLabelResolutionTest(TestCase):
    """Task 7's N+1 guard: a StepNote's `target` is a GenericForeignKey that
    can point at any of RequestMain/Oferta/Zlecenie/Wniosek, or nothing.
    Resolving it per-row would fan out into one query per note on a company
    card with many persons — assertNumQueries pins the fixed query count."""

    def setUp(self):
        self.company = Company.objects.create(name="Zetom Sp. z o.o.", nip="1234563218")

    def test_company_history_resolves_every_target_type_without_n_plus_one(self):
        request_main = RequestMain.objects.create(**BASE_REQ)
        oferta = Oferta.objects.create(**BASE_REQ)
        zlecenie = Zlecenie.objects.create(**BASE_REQ)
        wniosek = Wniosek.objects.create(**BASE_REQ)
        targets = [request_main, oferta, zlecenie, wniosek, None]
        for i, target in enumerate(targets):
            person = Client.objects.create(first_name=f"Person{i}")
            CompanyPersonLink.objects.create(company=self.company, person=person)
            create_step_note(
                author=None, kind=StepNote.Kind.CONTACT, text=f"Kontakt {i}",
                person=person, contacted_at=timezone.now(), target=target,
            )

        with self.assertNumQueries(5):
            rows = contact_rows_for_company(self.company)

        self.assertEqual(len(rows), 5)
        labels = {row["summary"]: row["zaglowek"] for row in rows}
        self.assertIn(str(request_main.pk), labels["Kontakt 0"])
        self.assertIn(str(oferta.pk), labels["Kontakt 1"])
        self.assertIn(str(zlecenie.pk), labels["Kontakt 2"])
        self.assertIn(str(wniosek.pk), labels["Kontakt 3"])
        self.assertEqual(labels["Kontakt 4"], "")


# claude — Task 9: write side. Both endpoints are addressed by PERSON pk
# (see task-9-brief.md — the Company card has no urls of its own, its
# "Dodaj kontakt" flow picks a person first and posts to the same url).
class ClientStepNoteEndpointsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff9", "s9@s.pl", "pass12345")
        self.client.force_login(self.user)
        self.person = Client.objects.create(first_name="Jan", last_name="Kowalski")
        self.create_url = reverse(
            "admin:clients_client_step_note_create", args=[self.person.pk],
        )

    def test_create_contact_from_person_card(self):
        resp = self.client.post(
            self.create_url,
            {"text": "Rozmowa telefoniczna", "channel": StepNote.Channel.CALL},
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(resp.status_code, 302)
        note = StepNote.objects.get()
        self.assertEqual(note.kind, StepNote.Kind.CONTACT)
        self.assertEqual(note.person_id, self.person.pk)
        self.assertEqual(note.text, "Rozmowa telefoniczna")
        self.assertIsNotNone(note.contacted_at)

    # claude — Fix-round: the shared modal posts `kind`, but this form had no
    # such field and the view hardcoded kind=CONTACT. Picking "Przypomnienie"
    # on a person card returned 302 "Step note added" and silently wrote a
    # CONTACT with a fabricated contacted_at=now: no reminder existed,
    # "Zaplanowane" stayed empty, and a conversation that never happened
    # showed up in "Historia kontaktów".
    def test_create_reminder_from_person_card(self):
        due = timezone.now() + timedelta(days=3)

        resp = self.client.post(
            self.create_url,
            {
                "kind": StepNote.Kind.REMINDER,
                "next_contact_at": timezone.localtime(due).strftime("%Y-%m-%dT%H:%M"),
                "action": "Oddzwonić w sprawie oferty",
                "text": "Klient prosił o telefon w przyszłym tygodniu",
            },
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(resp.status_code, 302)
        note = StepNote.objects.get()
        self.assertEqual(note.kind, StepNote.Kind.REMINDER)
        self.assertEqual(note.person_id, self.person.pk)
        self.assertEqual(note.action, "Oddzwonić w sprawie oferty")
        self.assertIsNotNone(note.next_contact_at)
        # a reminder is not a conversation — nothing may be invented here
        self.assertIsNone(note.contacted_at)

    def test_reminder_from_person_card_lands_in_zaplanowane(self):
        due = timezone.now() + timedelta(days=3)

        self.client.post(
            self.create_url,
            {
                "kind": StepNote.Kind.REMINDER,
                "next_contact_at": timezone.localtime(due).strftime("%Y-%m-%dT%H:%M"),
                "action": "Oddzwonić",
            },
            HTTP_HOST="127.0.0.1",
        )

        rows = reminder_rows_for_person(self.person)
        self.assertEqual([row["note_pk"] for row in rows], [StepNote.objects.get().pk])
        # ...and not in the contact history, which is for conversations only
        self.assertEqual(contact_rows_for_person(self.person), [])

    # claude — the reminder invariant (kind=reminder => next_contact_at) is
    # enforced by StepNote.clean()/CheckConstraint via create_step_note(); the
    # view must surface that as an error, never as a note that isn't there.
    def test_reminder_without_due_date_is_rejected(self):
        resp = self.client.post(
            self.create_url,
            {"kind": StepNote.Kind.REMINDER, "action": "Bez daty"},
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(StepNote.objects.count(), 0)

    def test_create_contact_with_related_request_sets_target(self):
        request_main = RequestMain.objects.create(**BASE_REQ)
        RequestClientLink.objects.create(request=request_main, client=self.person)

        resp = self.client.post(
            self.create_url,
            {"text": "Omówiono zamówienie", "target": request_main.pk},
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(resp.status_code, 302)
        note = StepNote.objects.get()
        self.assertEqual(note.target_object_id, request_main.pk)
        self.assertEqual(
            note.target_content_type, ContentType.objects.get_for_model(RequestMain),
        )

    # claude — security: `target` arrives as a raw pk in POST data. A request
    # that is NOT linked to this client must be rejected outright — otherwise
    # a crafted pk attaches a note to an unrelated customer's request.
    def test_create_contact_rejects_unrelated_request(self):
        unrelated_request = RequestMain.objects.create(**BASE_REQ)
        # deliberately not linked to self.person via RequestClientLink

        resp = self.client.post(
            self.create_url,
            {"text": "Próba podpięcia cudzej sprawy", "target": unrelated_request.pk},
            HTTP_HOST="127.0.0.1",
        )

        self.assertIn(resp.status_code, (302, 403))
        self.assertEqual(StepNote.objects.count(), 0)
        self.assertFalse(
            StepNote.objects.filter(
                target_content_type=ContentType.objects.get_for_model(RequestMain),
                target_object_id=unrelated_request.pk,
            ).exists()
        )

    def test_view_only_user_cannot_create_note(self):
        viewer = User.objects.create_user(
            "viewer9", "v9@v.pl", "pass12345", is_staff=True,
        )
        profile = viewer.profile
        profile.otp_exempt = True
        # claude — drop the default role (carries edit_clients) so
        # effective_permissions() reflects only the extra we add below.
        profile.role = None
        profile.save()
        profile.extra_permissions.add(Permission.objects.get(code="view_clients"))
        self.client.force_login(viewer)

        resp = self.client.post(
            self.create_url, {"text": "x"}, HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(StepNote.objects.count(), 0)

    def test_get_request_does_not_create_note(self):
        resp = self.client.get(self.create_url, HTTP_HOST="127.0.0.1")

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(StepNote.objects.count(), 0)

    def test_done_endpoint_closes_reminder(self):
        note = create_step_note(
            author=self.user, kind=StepNote.Kind.REMINDER, text="Oddzwonić",
            person=self.person, next_contact_at=timezone.now() + timedelta(days=1),
        )
        done_url = reverse(
            "admin:clients_client_step_note_done", args=[self.person.pk, note.pk],
        )

        resp = self.client.post(done_url, {}, HTTP_HOST="127.0.0.1")

        self.assertEqual(resp.status_code, 302)
        note.refresh_from_db()
        self.assertIsNotNone(note.done_at)
        self.assertEqual(reminder_rows_for_person(self.person), [])

    # claude — Fix-round: `done` exercises a different view function than
    # `create` (step_note_done_action vs step_note_create_action) and had no
    # coverage of its own. Same real-profile pattern as
    # test_view_only_user_cannot_create_note — no mocking user_has_perm.
    def test_view_only_user_cannot_close_reminder(self):
        note = create_step_note(
            author=self.user, kind=StepNote.Kind.REMINDER, text="Oddzwonić",
            person=self.person, next_contact_at=timezone.now() + timedelta(days=1),
        )
        done_url = reverse(
            "admin:clients_client_step_note_done", args=[self.person.pk, note.pk],
        )
        viewer = User.objects.create_user(
            "viewer9b", "v9b@v.pl", "pass12345", is_staff=True,
        )
        profile = viewer.profile
        profile.otp_exempt = True
        profile.role = None
        profile.save()
        profile.extra_permissions.add(Permission.objects.get(code="view_clients"))
        self.client.force_login(viewer)

        resp = self.client.post(done_url, {}, HTTP_HOST="127.0.0.1")

        self.assertEqual(resp.status_code, 403)
        note.refresh_from_db()
        self.assertIsNone(note.done_at)

    def test_get_done_request_does_not_close_reminder(self):
        note = create_step_note(
            author=self.user, kind=StepNote.Kind.REMINDER, text="Oddzwonić",
            person=self.person, next_contact_at=timezone.now() + timedelta(days=1),
        )
        done_url = reverse(
            "admin:clients_client_step_note_done", args=[self.person.pk, note.pk],
        )

        resp = self.client.get(done_url, HTTP_HOST="127.0.0.1")

        self.assertEqual(resp.status_code, 302)
        note.refresh_from_db()
        self.assertIsNone(note.done_at)

    # claude — mark_reminder_done() rejects kind=contact with ValidationError;
    # the view must turn that into messages.error + redirect, not a 500.
    def test_done_endpoint_rejects_contact_note(self):
        note = create_step_note(
            author=self.user, kind=StepNote.Kind.CONTACT, text="Rozmowa",
            person=self.person, contacted_at=timezone.now(),
        )
        done_url = reverse(
            "admin:clients_client_step_note_done", args=[self.person.pk, note.pk],
        )

        resp = self.client.post(done_url, {}, HTTP_HOST="127.0.0.1")

        self.assertEqual(resp.status_code, 302)
        note.refresh_from_db()
        self.assertIsNone(note.done_at)

    # claude — same class of cross-customer write the `target` check guards
    # against on create: a note that belongs to a different client than the
    # person pk in the url must not be closeable through this url.
    def test_done_endpoint_rejects_note_of_a_different_client(self):
        other_person = Client.objects.create(first_name="Anna", last_name="Nowak")
        note = create_step_note(
            author=self.user, kind=StepNote.Kind.REMINDER, text="Cudze przypomnienie",
            person=other_person, next_contact_at=timezone.now() + timedelta(days=1),
        )
        done_url = reverse(
            "admin:clients_client_step_note_done", args=[self.person.pk, note.pk],
        )

        resp = self.client.post(done_url, {}, HTTP_HOST="127.0.0.1")

        self.assertEqual(resp.status_code, 403)
        note.refresh_from_db()
        self.assertIsNone(note.done_at)


# claude — Task 9 ADDED REQUIREMENT: both cards must feed the shared
# work-log modal template (crm/zetom/templates/admin/zetom/shared/
# step_notes_modal.html) the same four context keys the zetom-side cards
# already provide, so a later task's modal doesn't render empty/crash.
class ClientCardModalContextTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff9b", "s9b@s.pl", "pass12345")
        self.client.force_login(self.user)

    def test_client_card_context_provides_modal_keys(self):
        person = Client.objects.create(first_name="Jan", last_name="Kowalski")
        company = Company.objects.create(name="Zetom Sp. z o.o.", nip="1234563218")
        CompanyPersonLink.objects.create(company=company, person=person)

        person_resp = self.client.get(
            reverse("admin:clients_client_change", args=[person.pk]),
            HTTP_HOST="127.0.0.1",
        )
        self.assertEqual(person_resp.status_code, 200)
        for key in (
            "step_notes_enabled", "step_notes_create_url",
            "step_notes_target_label", "step_notes_persons",
        ):
            self.assertIn(key, person_resp.context)
        self.assertTrue(person_resp.context["step_notes_enabled"])
        self.assertEqual(
            person_resp.context["step_notes_create_url"],
            reverse("admin:clients_client_step_note_create", args=[person.pk]),
        )
        self.assertEqual(list(person_resp.context["step_notes_persons"]), [person])

        company_resp = self.client.get(
            reverse("admin:clients_company_change", args=[company.pk]),
            HTTP_HOST="127.0.0.1",
        )
        self.assertEqual(company_resp.status_code, 200)
        for key in (
            "step_notes_enabled", "step_notes_create_url",
            "step_notes_target_label", "step_notes_persons",
        ):
            self.assertIn(key, company_resp.context)
        self.assertTrue(company_resp.context["step_notes_enabled"])
        self.assertIn(person, list(company_resp.context["step_notes_persons"]))

    # claude — Fix-round: neither card context carried `step_notes`, the key
    # the shared modal iterates for its timeline, so the modal permanently
    # showed "No notes yet." even on a client with a full contact history.
    def test_client_cards_feed_the_modal_timeline(self):
        person = Client.objects.create(first_name="Jan", last_name="Kowalski")
        company = Company.objects.create(name="Zetom Sp. z o.o.", nip="1234563218")
        CompanyPersonLink.objects.create(company=company, person=person)
        request_main = RequestMain.objects.create(**BASE_REQ)
        create_step_note(
            author=self.user, kind=StepNote.Kind.CONTACT,
            text="Rozmowa o kalibracji", person=person,
            contacted_at=timezone.now(), target=request_main,
        )

        for url in (
            reverse("admin:clients_client_change", args=[person.pk]),
            reverse("admin:clients_company_change", args=[company.pk]),
        ):
            with self.subTest(url=url):
                resp = self.client.get(url, HTTP_HOST="127.0.0.1")

                self.assertEqual(resp.status_code, 200)
                self.assertIn("step_notes", resp.context)
                self.assertEqual(
                    [note.text for note in resp.context["step_notes"]],
                    ["Rozmowa o kalibracji"],
                )
                # the note's request label must resolve, like it does in the
                # zetom-side timeline (entry.stage_label)
                self.assertIn(
                    str(request_main.pk), resp.context["step_notes"][0].stage_label,
                )
                self.assertNotContains(resp, "No notes yet.")

    def test_open_reminders_stay_out_of_the_client_card_timeline(self):
        # the client cards render their own "Zaplanowane" panel; an open
        # reminder must not be duplicated into the modal's history list.
        person = Client.objects.create(first_name="Jan", last_name="Kowalski")
        create_step_note(
            author=self.user, kind=StepNote.Kind.REMINDER, text="Oddzwonić",
            person=person, next_contact_at=timezone.now() + timedelta(days=1),
        )

        resp = self.client.get(
            reverse("admin:clients_client_change", args=[person.pk]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(list(resp.context["step_notes"]), [])
