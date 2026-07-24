#!/bin/sh
set -e

echo "Waiting for postgres at ${DB_HOST}:${DB_PORT}..."
until python -c "import socket; s = socket.socket(); s.settimeout(2); s.connect(('${DB_HOST}', int('${DB_PORT}')))" 2>/dev/null; do
  sleep 1
done
echo "Postgres is up"

if [ "${SKIP_DJANGO_INIT:-0}" != "1" ]; then
  python manage.py migrate --noinput
  python manage.py compilemessages
  python manage.py collectstatic --noinput --clear
else
  echo "Skipping Django init tasks (SKIP_DJANGO_INIT=1)"
fi

exec "$@"
