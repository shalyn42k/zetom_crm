import logging
import os
import sys
import threading
import time

from django.conf import settings

from crm.notification.services.followup_reminders import process_due_followups
from crm.notification.services.stale_request_reminders import process_stale_requests

logger = logging.getLogger(__name__)
_thread_started = False


def start_followup_scheduler():
    global _thread_started

    if _thread_started:
        return
    if not getattr(settings, "FOLLOWUP_REMINDERS_AUTOSTART", False):
        return
    if "runserver" not in sys.argv:
        return
    # Django autoreload launches a parent and a child process; run scheduler
    # only in the serving child process.
    if os.environ.get("RUN_MAIN") != "true":
        return

    interval = max(int(getattr(settings, "FOLLOWUP_REMINDERS_INTERVAL_SECONDS", 60)), 10)

    def _loop():
        logger.info("followup scheduler started (interval=%ss)", interval)
        while True:
            try:
                processed, created = process_due_followups()
                if processed or created:
                    logger.info(
                        "followup scheduler: processed=%s created=%s",
                        processed,
                        created,
                    )
            except Exception:
                logger.exception("followup scheduler failed")
            try:
                stale_created = process_stale_requests()
                if stale_created:
                    logger.info("followup scheduler: stale-request reminders=%s", stale_created)
            except Exception:
                logger.exception("stale-request reminder scheduler failed")
            time.sleep(interval)

    thread = threading.Thread(
        target=_loop,
        name="followup-reminders-scheduler",
        daemon=True,
    )
    thread.start()
    _thread_started = True
