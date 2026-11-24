#!/bin/sh
set -eu

INTERVAL="${FOLLOWUP_REMINDERS_INTERVAL_SECONDS:-60}"

case "$INTERVAL" in
  ''|*[!0-9]*)
    echo "Invalid FOLLOWUP_REMINDERS_INTERVAL_SECONDS='$INTERVAL', fallback to 60"
    INTERVAL=60
    ;;
esac

if [ "$INTERVAL" -lt 10 ]; then
  INTERVAL=10
fi

echo "Follow-up scheduler started (interval=${INTERVAL}s)"

while true; do
  python manage.py create_followup_reminders || true
  sleep "$INTERVAL"
done
