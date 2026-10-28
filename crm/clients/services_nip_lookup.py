# claude
"""Company data by Polish NIP from the Ministry of Finance VAT register
("Biała lista podatników VAT", https://wl-api.mf.gov.pl) — public, no API
key. Returns name, REGON, KRS, VAT status and the working (or registered)
address split into street / post code / city.

The register has a daily request limit per caller, so answers are cached
for a day. Network or register errors come back as a NipLookupError with a
message meant for the person at the screen.
"""
import re

import requests
from django.core.cache import cache
from django.utils import timezone
from django.utils.translation import gettext as _

from crm.clients.validators import normalize_nip, validate_nip

API_URL = "https://wl-api.mf.gov.pl/api/search/nip/{nip}"
TIMEOUT_SECONDS = 8
CACHE_SECONDS = 24 * 60 * 60

# "UL. PRZEMYSŁOWA 12, 00-001 WARSZAWA" -> street, post code, city
_ADDRESS_RE = re.compile(r"^(?P<street>.*?),\s*(?P<post>\d{2}-\d{3})\s+(?P<city>.+)$")


class NipLookupError(Exception):
    pass


def split_address(address):
    address = (address or "").strip()
    match = _ADDRESS_RE.match(address)
    if not match:
        return {"street": address, "post_code": "", "city": ""}
    return {
        "street": match.group("street").strip(),
        "post_code": match.group("post"),
        "city": match.group("city").strip(),
    }


def _title(text):
    """The register writes everything in capitals; make it readable but keep
    legal-form abbreviations (SP. Z O.O., S.A.) as people write them."""
    if not text:
        return ""
    if text.upper() != text:
        return text
    words = []
    for word in text.split():
        low = word.lower()
        if low in ("sp.", "z", "o.o.", "s.a.", "sp.j.", "sp.k.", "s.c."):
            words.append({"sp.": "Sp.", "z": "z", "o.o.": "o.o.", "s.a.": "S.A."}.get(low, low))
        else:
            words.append(word.capitalize())
    return " ".join(words)


def lookup_nip(raw_nip):
    try:
        validate_nip(raw_nip)  # format + official checksum, before any network call
        nip = normalize_nip(raw_nip)
    except Exception:
        raise NipLookupError(_("This is not a valid NIP."))
    if not nip:
        raise NipLookupError(_("This is not a valid NIP."))

    cache_key = f"nip-lookup:{nip}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        response = requests.get(
            API_URL.format(nip=nip),
            params={"date": timezone.localdate().isoformat()},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        raise NipLookupError(_("The tax register is not reachable right now. Try again later."))
    if response.status_code == 429:
        raise NipLookupError(_("The tax register's daily limit is used up. Try again tomorrow."))
    if response.status_code == 400:
        raise NipLookupError(_("This is not a valid NIP."))
    if response.status_code != 200:
        raise NipLookupError(_("The tax register is not reachable right now. Try again later."))

    subject = ((response.json() or {}).get("result") or {}).get("subject")
    if not subject:
        raise NipLookupError(_("No company with this NIP in the tax register."))

    address = subject.get("workingAddress") or subject.get("residenceAddress") or ""
    data = {
        "nip": nip,
        "name": _title(subject.get("name") or ""),
        "regon": subject.get("regon") or "",
        "krs": subject.get("krs") or "",
        "status_vat": subject.get("statusVat") or "",
        "address": address,
        "country": "Polska",
        **{k: _title(v) if k != "post_code" else v for k, v in split_address(address).items()},
    }
    cache.set(cache_key, data, CACHE_SECONDS)
    return data
