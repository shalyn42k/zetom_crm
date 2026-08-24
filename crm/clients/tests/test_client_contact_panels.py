# claude
"""Task 7: contact-history and reminders row-builders that read StepNote
instead of ClientInteraction.

See .superpowers/sdd/2026-08-24-step-notes-unification/task-7-brief.md.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from crm.clients.models import Client, Company, CompanyPersonLink
from crm.clients.services_contacts import (
    contact_rows_for_company, contact_rows_for_person,
    reminder_rows_for_company, reminder_rows_for_person,
)
from crm.zetom.models import Oferta, RequestMain, StepNote, Wniosek, Zlecenie
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
