# claude — real client IP behind the Cloudflare tunnel.
#
# In production every request reaches gunicorn from the cloudflared
# container, so REMOTE_ADDR is the same internal address for everybody.
# Anything keyed on it (django-axes lockouts, the public form throttle)
# then treats all users as one: five bad passwords from anyone locked the
# whole office out. Cloudflare puts the visitor's address into
# CF-Connecting-IP and overwrites any value a client sends, and the web
# container has no published port (docker-compose.prod.yml), so the header
# can't be forged by going around the tunnel.
from django.conf import settings


def get_client_ip(request):
    if getattr(settings, "TRUST_CF_CONNECTING_IP", False):
        forwarded = request.META.get("HTTP_CF_CONNECTING_IP", "").strip()
        if forwarded:
            return forwarded
    return request.META.get("REMOTE_ADDR") or None
