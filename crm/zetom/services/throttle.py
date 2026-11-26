# claude — simple fixed-window throttle for the anonymous public form
# (/zetom/email/). Without it a bot could create unlimited RequestNull rows
# and staff e-mails. Keyed on the visitor IP (config/client_ip.py, real IP
# behind Cloudflare). Uses the default cache: per gunicorn process, so the
# real ceiling is the limit times the number of workers, which is fine for
# stopping a flood.
from django.conf import settings
from django.core.cache import cache

from config.client_ip import get_client_ip

WINDOW_SECONDS = 3600


def public_form_allowed(request):
    """Count this submission; False once the IP is over the hourly limit."""
    limit = settings.PUBLIC_FORM_RATE_PER_HOUR
    if limit <= 0:
        return True
    key = f"public-form:{get_client_ip(request) or 'unknown'}"
    cache.add(key, 0, WINDOW_SECONDS)
    try:
        count = cache.incr(key)
    except ValueError:  # expired between add and incr
        cache.set(key, 1, WINDOW_SECONDS)
        count = 1
    return count <= limit
