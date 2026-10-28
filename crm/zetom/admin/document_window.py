# claude
"""The document window shared by Oferta / Zlecenie / Wniosek admins.

Layout (templates/admin/zetom/shared/document_change_form.html), per the
approved redesign (docs/superpowers/specs/2026-10-27-requests-declutter-
design.md): small buttons on top, the template's own fields on the left,
the document on the right, the team's files underneath.

Every action leaves a trace where the project already keeps one: files and
created document versions list who and when, reminders go to the work log
(Dziennik kontaktów), mark-done/delete to the request history.

The document text itself is a placeholder until the real templates arrive;
"Create document" saves the current sheet as an HTML file (open it and
print → "Save as PDF").
"""
import json

from django.contrib import messages
from django.core.files.base import ContentFile
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import path, reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from crm.notification.services.request_mail import document_code
from crm.zetom.models import RequestAttachment

DOCUMENT_TITLES = {
    "Oferta": _("Offer"),
    "Zlecenie": _("Order"),
    "Wniosek": _("Application"),
}

# max size of one uploaded file (bytes); the same limit applies to every
# document kind.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def document_context(obj, user):
    """What the paper (preview, print page, saved version) renders. Kept
    free of request state so all three can never disagree."""
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
        # claude — channel code -> Polish phrase, for the live preview of the offer
        "inquiry_phrases_json": json.dumps(getattr(type(obj), "INQUIRY_PHRASES_PL", {}), ensure_ascii=False),
    }


class DocumentWindowMixin:
    change_form_template = "admin/zetom/shared/document_change_form.html"
    # Oferta / Wniosek can be closed by hand; Zlecenie only through the chain.
    can_mark_done = False

    def get_urls(self):
        urls = super().get_urls()
        opts = self.model._meta
        prefix = f"{opts.app_label}_{opts.model_name}"
        wrap = self.admin_site.admin_view
        return [
            path("<path:object_id>/print/", wrap(self.print_view), name=f"{prefix}_print"),
            path("<path:object_id>/files/upload/", wrap(self.upload_files_action), name=f"{prefix}_upload_files"),
            path(
                "<path:object_id>/files/<int:attachment_id>/delete/",
                wrap(self.delete_file_action),
                name=f"{prefix}_delete_file",
            ),
            path("<path:object_id>/create-document/", wrap(self.create_document_action), name=f"{prefix}_create_document"),
        ] + urls

    # ---- helpers ---------------------------------------------------------

    def _fk_name(self):
        return self.model._meta.model_name  # "oferta" / "zlecenie" / "wniosek"

    def _change_url(self, obj_or_id):
        opts = self.model._meta
        pk = getattr(obj_or_id, "pk", obj_or_id)
        return reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[pk])

    def _get_doc(self, request, object_id, *, change=False):
        obj = self.get_queryset(request).filter(pk=object_id).first()
        if obj is None:
            raise Http404
        allowed = self.has_change_permission(request, obj) if change else self.has_view_permission(request, obj)
        return obj, allowed

    def _files(self, obj):
        return list(
            RequestAttachment.objects.filter(**{self._fk_name(): obj})
            .select_related("uploaded_by")
            .order_by("-uploaded_at")
        )

    def _files_with_urls(self, obj, prefix):
        files = self._files(obj)
        for att in files:
            att.delete_url = reverse(f"{prefix}_delete_file", args=[obj.pk, att.pk])
        return files

    # ---- views -----------------------------------------------------------

    def print_view(self, request, object_id):
        obj, allowed = self._get_doc(request, object_id)
        if not allowed:
            raise Http404
        return render(request, "admin/zetom/shared/document_print.html", document_context(obj, request.user))

    def upload_files_action(self, request, object_id):
        if request.method != "POST":
            return redirect(self._change_url(object_id))
        obj, allowed = self._get_doc(request, object_id, change=True)
        if not allowed:
            return HttpResponseForbidden(_("You don't have permission for this action."))
        files = request.FILES.getlist("files")
        if not files:
            messages.error(request, _("No files selected."))
            return redirect(self._change_url(obj) + "#files")
        too_big = [f.name for f in files if f.size > MAX_UPLOAD_BYTES]
        if too_big:
            messages.error(request, _("Too large (max 20 MB): %(names)s") % {"names": ", ".join(too_big)})
            return redirect(self._change_url(obj) + "#files")
        for f in files:
            RequestAttachment.objects.create(**{self._fk_name(): obj}, file=f, uploaded_by=request.user)
        messages.success(request, _("%(n)d file(s) uploaded.") % {"n": len(files)})
        return redirect(self._change_url(obj) + "#files")

    def delete_file_action(self, request, object_id, attachment_id):
        if request.method != "POST":
            return redirect(self._change_url(object_id))
        obj, allowed = self._get_doc(request, object_id, change=True)
        if not allowed:
            return HttpResponseForbidden(_("You don't have permission for this action."))
        att = RequestAttachment.objects.filter(pk=attachment_id, **{self._fk_name(): obj}).first()
        if att is not None:
            att.file.delete(save=False)
            att.delete()
            messages.success(request, _("Attachment deleted."))
        return redirect(self._change_url(obj) + "#files")

    def create_document_action(self, request, object_id):
        """Save the current sheet as a new file version in the files list."""
        if request.method != "POST":
            return redirect(self._change_url(object_id))
        obj, allowed = self._get_doc(request, object_id, change=True)
        if not allowed:
            return HttpResponseForbidden(_("You don't have permission for this action."))
        paper = document_context(obj, request.user)
        html = render_to_string("admin/zetom/shared/document_print.html", paper, request=request)
        version = sum(
            1 for a in self._files(obj) if a.file.name.rsplit("/", 1)[-1].startswith(slugify(paper["doc_code"]))
        ) + 1
        name = f"{slugify(paper['doc_code'])}-v{version}.html"
        RequestAttachment.objects.create(
            **{self._fk_name(): obj}, file=ContentFile(html.encode("utf-8"), name=name), uploaded_by=request.user,
        )
        messages.success(request, _("Document saved to files: %(name)s") % {"name": name})
        return redirect(self._change_url(obj) + "#files")

    # ---- page context ----------------------------------------------------

    def render_change_form(self, request, context, *args, **kwargs):
        obj = context.get("original")
        if obj is not None and obj.pk:
            context["doc_window"] = self._doc_window_context(request, obj)
        return super().render_change_form(request, context, *args, **kwargs)

    def _doc_window_context(self, request, obj):
        opts = self.model._meta
        prefix = f"admin:{opts.app_label}_{opts.model_name}"
        paper = document_context(obj, request.user)
        parent = paper["parent"]
        can_change = self.has_change_permission(request, obj)
        return {
            **paper,
            "status_label": obj.get_status_display(),
            # claude — the offer's own number leads the header when it has one
            "title_number": getattr(obj, "offer_number", "") or "",
            "parent_url": reverse("admin:zetom_requestmain_change", args=[parent.pk]) if parent else "",
            "parent_code": f"REQ-{parent.created_at.year}-{parent.pk:04d}" if parent else "",
            "print_url": reverse(f"{prefix}_print", args=[obj.pk]),
            "mark_done_url": (
                reverse(f"{prefix}_mark_done", args=[obj.pk])
                if self.can_mark_done and obj.status != "done" and can_change else ""
            ),
            "delete_url": reverse(f"{prefix}_delete", args=[obj.pk]) if self.has_delete_permission(request, obj) else "",
            "can_change": can_change,
            "files": self._files_with_urls(obj, prefix),
            "upload_url": reverse(f"{prefix}_upload_files", args=[obj.pk]),
            "create_document_url": reverse(f"{prefix}_create_document", args=[obj.pk]),
            "notes_count": obj.step_notes.count(),
        }
