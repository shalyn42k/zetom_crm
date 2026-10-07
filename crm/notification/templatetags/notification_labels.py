"""Template filters for inapp notification bodies — resolve a raw payload
code to its translated label at render time (not when the payload is
written), same reasoning as status_manager.templatetags.status_labels:
a notification is read later, possibly by someone with a different active
language than whoever triggered it, so the label can't be baked in up front.
"""
from django import template
from django.utils.translation import gettext

register = template.Library()

# claude — mirrors DECISION_APPROVED/DECISION_REJECTED in
# crm/zetom/admin/requestmain_resolve_review.py (ResolveReviewForm's
# DECISION_CHOICES). Not imported from there directly — that module is an
# admin view, not something a template filter should depend on — but the
# two codes themselves are a stable, two-value vocabulary, and the English
# labels here are the exact same msgids already in the catalog.
_DECISION_LABELS = {
    "approved": lambda: gettext("Approved"),
    "rejected": lambda: gettext("Rejected"),
}


@register.filter
def review_decision_label(code):
    labeler = _DECISION_LABELS.get(code)
    return labeler() if labeler else code
