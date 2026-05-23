"""Two POST endpoints for "Actions → Mail" on the RequestMain change form.

Plug-in as a mixin onto `RequestMainAdmin`:
  - `mail/document/` sends the type-specific staff letter for an existing
    Oferta/Zlecenie/Wniosek.
  - `mail/freeform/` sends a free-form letter to the client.

Rendering + SMTP live in `crm.notification.services`. This file only parses
the POST, validates state, shows messages, and redirects back.
"""
# Django imports
from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import path
from django.utils.translation import gettext_lazy as _

# Local imports
from crm.notification.services import request_mail
from crm.status_manager.services.statuses import Status
from crm.zetom.models import Oferta, RequestMain, Wniosek, Zlecenie

# claude
KIND_TO_MODEL = {
    "oferta": Oferta,
    "zlecenie": Zlecenie,
    "wniosek": Wniosek,
}


# claude
class FreeformMailForm(forms.Form):
    subject = forms.CharField(max_length=200)
    body = forms.CharField(widget=forms.Textarea)


# claude
class RequestMailMixin:
    """Adds /mail/document/ and /mail/freeform/ routes to RequestMainAdmin."""

    def get_urls(self):
        urls = super().get_urls()
        view = self.admin_site.admin_view
        custom = [
            path(
                "<path:object_id>/mail/document/",
                view(self.mail_document_action),
                name="zetom_requestmain_mail_document",
            ),
            path(
                "<path:object_id>/mail/freeform/",
                view(self.mail_freeform_action),
                name="zetom_requestmain_mail_freeform",
            ),
        ]
        return custom + urls

    def mail_document_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)
        obj = get_object_or_404(RequestMain, pk=object_id)

        kind = (request.POST.get("kind") or "").lower()
        doc_model = KIND_TO_MODEL.get(kind)
        if doc_model is None:
            messages.error(request, _("Invalid document kind."))
            return redirect("admin:zetom_requestmain_change", object_id)

        document_id = request.POST.get("document_id")
        document = doc_model.objects.filter(pk=document_id, from_main=obj).first()
        if document is None:
            messages.error(request, _("Document not found for this request."))
            return redirect("admin:zetom_requestmain_change", object_id)

        # Defence-in-depth: request_mail.send_document_to_staff also checks this,
        # but we surface a user-facing error here so the form doesn't silently
        # do nothing.
        if document.status != Status.in_progress:
            messages.error(request, _("Document must be in progress to send."))
            return redirect("admin:zetom_requestmain_change", object_id)

        request_mail.send_document_to_staff(document, actor=request.user)
        messages.success(request, _("Mail sent. Document moved to waiting."))
        return redirect("admin:zetom_requestmain_change", object_id)

    def mail_freeform_action(self, request, object_id):
        if request.method != "POST":
            return redirect("admin:zetom_requestmain_change", object_id)
        obj = get_object_or_404(RequestMain, pk=object_id)

        form = FreeformMailForm(request.POST)
        if not form.is_valid():
            messages.error(request, _("Subject and body are required."))
            return redirect("admin:zetom_requestmain_change", object_id)

        request_mail.send_freeform_to_client(
            request_main=obj,
            subject=form.cleaned_data["subject"],
            body=form.cleaned_data["body"],
            from_user=request.user,
        )
        messages.success(request, _("Mail sent to client."))
        return redirect("admin:zetom_requestmain_change", object_id)
