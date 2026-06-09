# claude
"""Request-to-request duplicate finder for the Validation Window.

`find_request_duplicates(src)` ranks other *requests* (RequestNull +
RequestMain) by how strongly they match `src`. It's the sibling of
`duplicate_matcher.find_candidates`, which matches a request against the
`Client` table; here both sides are request-shaped objects (they share the
RequestTemplate fields: first_name / last_name / phone / company_name /
company_nip / email), so the scoring compares like with like.

Used by the VW to warn "this looks like a copy of an existing request" and
to offer a hard-delete of the incoming RequestNull before it pollutes the DB.

Signals & weights mirror the Client matcher (max score capped at 100):
    exact phone        +50
    exact email        +40
    same NIP           +50
    same company       +20
    similar full name  +15
    same email domain  +10
"""
from __future__ import annotations

from dataclasses import dataclass, field

from crm.status_manager.services.statuses import RequestStatus
from crm.zetom.models import RequestMain, RequestNull
# Reuse the normalization helpers + badge vocabulary from the Client matcher
# so the two surfaces stay visually and semantically in sync.
from crm.zetom.services.duplicate_matcher import (
    BADGE_DOMAIN, BADGE_EXACT_EMAIL, BADGE_EXACT_PHONE, BADGE_SAME_COMPANY,
    BADGE_SAME_NIP, BADGE_SIMILAR_NAME, BADGE_WEAK, Badge, _email_domain,
    _name_similarity, _norm, _phone_str,
)

KIND_NULL = "null"
KIND_MAIN = "main"


@dataclass
class RequestCandidate:
    obj: object       # RequestNull or RequestMain
    kind: str         # KIND_NULL | KIND_MAIN
    score: int
    badges: list[Badge] = field(default_factory=list)

    @property
    def is_strong(self) -> bool:
        return self.score >= 70

    @property
    def is_weak(self) -> bool:
        return self.score < 50


def _score_pair(src, other) -> RequestCandidate:
    """Score `other` (a request) against `src` (a request)."""
    score = 0
    badges: list[Badge] = []

    src_phone, other_phone = _phone_str(src.phone), _phone_str(other.phone)
    if src_phone and other_phone and src_phone == other_phone:
        score += 50
        badges.append(Badge.of(BADGE_EXACT_PHONE))

    src_email, other_email = _norm(src.email), _norm(other.email)
    if src_email and other_email and src_email == other_email:
        score += 40
        badges.append(Badge.of(BADGE_EXACT_EMAIL))

    src_nip = _norm(getattr(src, "company_nip", None))
    other_nip = _norm(getattr(other, "company_nip", None))
    if src_nip and other_nip and src_nip == other_nip:
        score += 50
        badges.append(Badge.of(BADGE_SAME_NIP))

    src_company, other_company = _norm(src.company_name), _norm(other.company_name)
    if src_company and other_company and src_company == other_company:
        score += 20
        badges.append(Badge.of(BADGE_SAME_COMPANY))

    src_name = f"{_norm(src.first_name)} {_norm(src.last_name)}".strip()
    other_name = f"{_norm(other.first_name)} {_norm(other.last_name)}".strip()
    if src_name and other_name and _name_similarity(src_name, other_name) >= 0.78:
        if not any(
            b.kind in (BADGE_EXACT_PHONE, BADGE_EXACT_EMAIL, BADGE_SAME_NIP)
            for b in badges
        ):
            score += 15
            badges.append(Badge.of(BADGE_SIMILAR_NAME))

    src_domain, other_domain = _email_domain(src.email), _email_domain(other.email)
    if (
        src_domain and other_domain
        and src_domain == other_domain
        and src_email != other_email
    ):
        score += 10
        badges.append(Badge.of(BADGE_DOMAIN))

    if not badges:
        badges.append(Badge.of(BADGE_WEAK))

    kind = KIND_MAIN if isinstance(other, RequestMain) else KIND_NULL
    return RequestCandidate(obj=other, kind=kind, score=min(score, 100), badges=badges)


def _prefilter(model, src):
    """Wide-net Q-prefilter so we don't scan the whole table every time."""
    from django.db.models import Q

    phone = _phone_str(src.phone)
    email = _norm(src.email)
    domain = _email_domain(src.email)
    company = _norm(src.company_name)
    last_name = _norm(src.last_name)
    nip = _norm(getattr(src, "company_nip", None))

    q = Q()
    if phone:
        q |= Q(phone=phone)
    if email:
        q |= Q(email__iexact=email)
    if domain:
        q |= Q(email__iendswith=f"@{domain}")
    if company:
        q |= Q(company_name__iexact=company)
    if last_name:
        q |= Q(last_name__iexact=last_name)
    if nip:
        q |= Q(company_nip=nip)
    if not q:
        return model.objects.none()
    return model.objects.filter(q)


def find_request_duplicates(src, limit: int = 6) -> list[RequestCandidate]:
    """Rank existing requests (RequestNull + active RequestMain) against `src`.

    `src` is a RequestNull or RequestMain. The source object itself is always
    excluded. Cancelled/deleted RequestMains are skipped — they're not live
    duplicates. Returns up to `limit` candidates, score-descending.
    """
    candidates: list[RequestCandidate] = []

    null_qs = _prefilter(RequestNull, src)
    if isinstance(src, RequestNull) and src.pk:
        null_qs = null_qs.exclude(pk=src.pk)
    candidates += [_score_pair(src, o) for o in null_qs[:200]]

    main_qs = _prefilter(RequestMain, src).exclude(
        status__in=[RequestStatus.cancelled, RequestStatus.deleted]
    )
    if isinstance(src, RequestMain) and src.pk:
        main_qs = main_qs.exclude(pk=src.pk)
    candidates += [_score_pair(src, o) for o in main_qs[:200]]

    candidates = [c for c in candidates if c.score > 0]
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:limit]
