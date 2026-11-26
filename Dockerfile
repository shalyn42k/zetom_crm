FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# gettext нужен Django для makemessages/compilemessages (переводы).
# pango/harfbuzz + шрифты — для WeasyPrint (документы в PDF): Liberation Sans
# метрически совпадает с Arial бланка оферты, Inter/DejaVu — для остальных,
# все с польскими буквами.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gettext \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
        fonts-liberation fonts-inter fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# /app/media is a volume in docker-compose.prod.yml (uploads must survive a
# redeploy); created here so the volume starts out owned by the app user.
RUN chmod +x docker/entrypoint.sh docker/followup_scheduler.sh \
    && useradd --create-home --shell /bin/bash app \
    && mkdir -p /app/media \
    && chown -R app:app /app
USER app

EXPOSE 8000

ENTRYPOINT ["./docker/entrypoint.sh"]
# gthread: 3 processes x 4 threads = 12 requests at once. Plain sync workers
# served only 3, so one slow call (SMTP, VAT register lookup) stalled a third
# of the site for everyone. max-requests recycles workers to cap memory.
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--worker-class", "gthread", \
     "--workers", "3", \
     "--threads", "4", \
     "--timeout", "120", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "100", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
