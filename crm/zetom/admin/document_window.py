# claude
"""The document window shared by Oferta / Zlecenie / Wniosek admins.

Wraps the normal change form in a two-column layout (see
templates/admin/zetom/shared/document_change_form.html): a compact form on
the left with only the fields the document template needs, and on the
right a live A4 preview, the print/PDF button and the messages & reminders
panel. The less-used fields (departments, assignees, source) sit in a
collapsed "Details" fieldset on the form itself.

Printing is the browser's own print dialog on a standalone page — "Save as
PDF" there gives the PDF without a server-side PDF library.
"""
from django.http import Http404
from django.shortcuts import render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from crm.notification.message_targets import build_composer_context
from crm.notification.services.request_mail import document_code

DOCUMENT_TITLES = {
    "Oferta": _("Offer"),
    "Zlecenie": _("Order"),
    "Wniosek": _("Application"),
}


def document_context(obj, user):
    """What the paper (preview and print) renders. Kept free of request
    state so the preview and the print page can never disagree."""
    kind = type(obj).__name__
    parent = getattr(obj, "from_main", None)
    signer = obj.assigned_to.first() if obj.pk else None
    signer = signer or user
    return {
        "doc": obj,
        "kind": kind,
        "doc_title": DOCUMENT_TITLES.get(kind, kind),
        "doc_code": document_code(obj) if obj.pk else "",
        "doc_date": timezone.localtime(obj.created_at) if obj.created_at else timezone.localtime(),
        "parent": parent,
        "signer_name": (signer.get_full_name() or signer.get_username()) if signer else "",
    }


class DocumentWindowMixin:
    change_form_template = "admin/zetom/shared/document_change_form.html"
    # Oferta / Wniosek can be closed by hand; Zlecenie only through the chain.
    can_mark_done = False

    def get_urls(self):
        urls = super().get_urls()
        opts = self.model._meta
        return [
            path(
                "<path:object_id>/print/",
                self.admin_site.admin_view(self.print_view),
                name=f"{opts.app_label}_{opts.model_name}_print",
            ),
        ] + urls

    def print_view(self, request, object_id):
        obj = self.get_queryset(request).filter(pk=object_id).first()
        if obj is None or not self.has_view_permission(request, obj):
            raise Http404
        return render(
            request,
            "admin/zetom/shared/document_print.html",
            document_context(obj, request.user),
        )

    def render_change_form(self, request, context, *args, **kwargs):
        obj = context.get("original")
        if obj is not None and obj.pk:
            context["doc_window"] = self._doc_window_context(request, obj)
        return super().render_change_form(request, context, *args, **kwargs)

    def _doc_window_context(self, request, obj):
        opts = self.model._meta
        paper = document_context(obj, request.user)
        parent = paper["parent"]
        mark_done_url = ""
        if self.can_mark_done and obj.status != "done" and self.has_change_permission(request, obj):
            mark_done_url = reverse(f"admin:{opts.app_label}_{opts.model_name}_mark_done", args=[obj.pk])
        return {
            **paper,
            "status_label": obj.get_status_display(),
            "parent_url": reverse("admin:zetom_requestmain_change", args=[parent.pk]) if parent else "",
            "print_url": reverse(f"admin:{opts.app_label}_{opts.model_name}_print", args=[obj.pk]),
            "mark_done_url": mark_done_url,
            "composer": build_composer_context(request, obj, paper["doc_code"]),
        }
