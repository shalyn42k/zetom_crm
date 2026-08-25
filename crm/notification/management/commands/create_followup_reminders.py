from django.core.management.base import BaseCommand

from crm.notification.services.followup_reminders import process_due_followups
from crm.notification.services.stale_request_reminders import process_stale_requests


class Command(BaseCommand):
    help = (
        "Create in-app reminders for due StepNote.next_contact_at dates, "
        "and for RequestMain rows nobody has picked up"
    )

    def handle(self, *args, **options):
        processed_notes, created_notifications = process_due_followups()
        stale_reminders = process_stale_requests()

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed notes: {processed_notes}; created notifications: {created_notifications}; "
                f"stale-request reminders: {stale_reminders}"
            )
        )
