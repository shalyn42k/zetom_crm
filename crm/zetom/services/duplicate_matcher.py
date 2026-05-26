# claude
"""Client duplicate matcher for the Validation Window.

`find_candidates(request_null)` ranks `Client` records by how strongly they
match the incoming `RequestNull`. The result drives the candidate list shown
on the validation screen (see handoff/README.md).

Signals & weights (max score capped at 100):
    exact phone        +50  badge "exact phone"        (green / strong)
    exact email        +40  badge "exact email"        (green / strong)
    same NIP           +50  badge "same NIP"           (blue  / org)
    same company       +20  badge "same company"       (purple)
    similar full name  +15  badge "similar name"       (purple / soft)
    same email domain  +10  badge "same email domain"  (slate / context)

The matcher is intentionally simple — string equality on normalized values
plus a difflib ratio for names. No DB indexes are required beyond the
existing ones (Client.company_nip already has `db_index=True`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from crm.clients.models import Client

# ---------------------------------------------------------------------------
# Badge variants — keep keys in sync with CSS (.mb.exact-phone etc.)
# ---------------------------------------------------------------------------

BADGE_EXACT_PHONE = "exact-phone"
BADGE_EXACT_EMAIL = "exact-email"
BADGE_SAME_NIP = "same-nip"
BADGE_SAME_COMPANY = "same-company"
BADGE_SIMILAR_NAME = "similar-name"
BADGE_DOMAIN = "domain"
BADGE_WEAK = "weak"

_BADGE_LABELS = {
    BADGE_EXACT_PHONE: _("exact phone"),
    BADGE_EXACT_EMAIL: _("exact email"),
    BADGE_SAME_NIP: _("same NIP"),
    BADGE_SAME_COMPANY: _("same company"),
    BADGE_SIMILAR_NAME: _("similar name"),
    BADGE_DOMAIN: _("same email domain"),
    BADGE_WEAK: _("no other signals"),
}


@dataclass
class Badge:
    kind: str  # one of BADGE_* keys above
    label: str

    @classmethod
    def of(cls, kind: str) -> "Badge":
        return cls(kind=kind, label=str(_BADGE_LABELS.get(kind, kind)))


@dataclass
class Candidate:
    client: Client
    score: int
    badges: list[Badge] = field(default_factory=list)
    # field-level highlights for the value column ({"phone": "+48...", ...})
    highlights: dict[str, str] = field(default_factory=dict)

    @property
    def is_strong(self) -> bool:
        return self.score >= 70

    @property
    def is_weak(self) -> bool:
        return self.score < 50


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _email_domain(value: Optional[str]) -> str:
    raw = _norm(value)
    return raw.split("@", 1)[1] if "@" in raw else ""


def _phone_str(phone) -> str:
    """Cast a PhoneNumberField value to string for comparison."""
    if not phone:
        return ""
    try:
        return str(phone)
    except Exception:
        return ""


def _name_similarity(a: str, b: str) -> float:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# A wide-net prefilter so we don't scan the whole Clients table every time.
# We pull anything that touches phone / email / NIP / company / surname,
# then rescore in Python.
def _candidate_queryset(rn) -> "models.QuerySet[Client]":
    phone = _phone_str(rn.phone)
    email = _norm(rn.email)
    domain = _email_domain(rn.email)
    company = _norm(rn.company_name)
    last_name = _norm(rn.last_name)

    q = Q()
    if phone:
        q |= Q(phone=phone)
    if email:
        q |= Q(email__iexact=email)
    if domain:
        q |= Q(email__iendswith=f"@{domain}")
    if company:
        q |= Q(company_name__icontains=company)
    if last_name:
        q |= Q(last_name__iexact=last_name)
    if not q:
        return Client.objects.none()
    return Client.objects.filter(q).distinct()


def _score_one(rn, client: Client) -> Candidate:
    score = 0
    badges: list[Badge] = []
    highlights: dict[str, str] = {}

    rn_phone = _phone_str(rn.phone)
    cl_phone = _phone_str(client.phone)
    if rn_phone and cl_phone and rn_phone == cl_phone:
        score += 50
        badges.append(Badge.of(BADGE_EXACT_PHONE))
        highlights["phone"] = cl_phone

    rn_email = _norm(rn.email)
    cl_email = _norm(client.email)
    if rn_email and cl_email and rn_email == cl_email:
        score += 40
        badges.append(Badge.of(BADGE_EXACT_EMAIL))
        highlights["email"] = client.email or ""

    rn_nip = _norm(getattr(rn, "company_nip", None))
    cl_nip = _norm(client.company_nip)
    if rn_nip and cl_nip and rn_nip == cl_nip:
        score += 50
        badges.append(Badge.of(BADGE_SAME_NIP))
        highlights["company_nip"] = client.company_nip or ""

    rn_company = _norm(rn.company_name)
    cl_company = _norm(client.company_name)
    if rn_company and cl_company and rn_company == cl_company:
        score += 20
        badges.append(Badge.of(BADGE_SAME_COMPANY))
        highlights["company_name"] = client.company_name or ""

    rn_fullname = f"{_norm(rn.first_name)} {_norm(rn.last_name)}".strip()
    cl_fullname = f"{_norm(client.first_name)} {_norm(client.last_name)}".strip()
    if rn_fullname and cl_fullname and _name_similarity(rn_fullname, cl_fullname) >= 0.78:
        # don't double-count if we already nailed phone+email+NIP
        if not any(b.kind in (BADGE_EXACT_PHONE, BADGE_EXACT_EMAIL, BADGE_SAME_NIP) for b in badges):
            score += 15
            badges.append(Badge.of(BADGE_SIMILAR_NAME))

    rn_domain = _email_domain(rn.email)
    cl_domain = _email_domain(client.email)
    if rn_domain and cl_domain and rn_domain == cl_domain and rn_email != cl_email:
        score += 10
        badges.append(Badge.of(BADGE_DOMAIN))

    if not badges:
        badges.append(Badge.of(BADGE_WEAK))

    return Candidate(
        client=client,
        score=min(score, 100),
        badges=badges,
        highlights=highlights,
    )


def find_candidates(rn, limit: int = 6) -> list[Candidate]:
    """Rank Client records by match strength against `rn` (RequestNull).

    Returns up to `limit` candidates, score-descending. An empty list means
    the duplicate matcher found nothing — the UI should fall back to the
    "Create as new client" path.
    """
    qs = _candidate_queryset(rn)
    candidates = [_score_one(rn, c) for c in qs[:200]]
    candidates = [c for c in candidates if c.score > 0]
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:limit]
