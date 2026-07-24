from django.core.management.base import BaseCommand

from crm.notification.services.followup_reminders import process_due_followups


class Command(BaseCommand):
    help = "Create in-app reminders for due StepNote.next_contact_at dates"

    def handle(self, *args, **options):
        processed_notes, created_notifications = process_due_followups()

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed notes: {processed_notes}; created notifications: {created_notifications}"
            )
        )
