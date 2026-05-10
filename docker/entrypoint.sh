#!/bin/sh
set -e

echo "Waiting for postgres at ${DB_HOST}:${DB_PORT}..."
until python -c "import socket; s = socket.socket(); s.settimeout(2); s.connect(('${DB_HOST}', int('${DB_PORT}')))" 2>/dev/null; do
  sleep 1
done
echo "Postgres is up"

python manage.py migrate --noinput
python manage.py collectstatic --noinput --clear

exec "$@"
