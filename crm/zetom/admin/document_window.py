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
import base64
import json
from email.mime.image import MIMEImage

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.validators import validate_email
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import path, reverse
from django.utils import timezone, translation
from django.utils.text import capfirst, slugify
from django.utils.translation import gettext_lazy as _

from crm.notification.services.request_mail import document_code
from crm.users.utils import user_has_perm
from crm.zetom.models import RequestAttachment, StepNote
from crm.zetom.services.reminder_targets import client_email_choices

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


# claude — the client data copied onto a document. Changing any of them on
# the document needs a note of where the new data came from (a contact-log
# entry), asked for by the "Skąd te dane?" dialog on save.
CLIENT_FIELDS = ("first_name", "last_name", "company_name", "company_nip", "email", "phone")


def _send_subject(obj, paper):
    number = getattr(obj, "offer_number", "") or paper["doc_code"]
    return f"{paper['doc_title']} {number} — ZETOM"


# Default mail text — Polish (the client's language), worded like the mails
# ZETOM staff send by hand. The signature is added below it on sending, so it
# is not part of the editable text.
_SEND_MESSAGES = {
    "Oferta": (
        "Dzień dobry.\n\nW załączniku umieściłem ofertę cenową {number} na wykonanie wzorcowania "
        "przyrządu pomiarowego wyszczególnionego w zapytaniu ofertowym."
    ),
    "Zlecenie": "Dzień dobry.\n\nW załączniku umieściłem zlecenie {number}.",
    "Wniosek": "Dzień dobry.\n\nW załączniku umieściłem wniosek {number}.",
}


def _send_message(obj, paper):
    number = getattr(obj, "offer_number", "") or paper["doc_code"]
    text = _SEND_MESSAGES.get(type(obj).__name__, "Dzień dobry.\n\nW załączniku umieściłem dokument {number}.")
    return text.format(number=number)


def signature(user):
    """The sender's mail signature: their own lines from the user profile,
    the company's from settings.COMPANY_SIGNATURE."""
    from crm.zetom.models import DepartmentsVariants

    profile = getattr(user, "profile", None)
    codes = (profile.main_departments or profile.departments) if profile else []
    labels = dict(DepartmentsVariants.choices)
    return {
        **settings.COMPANY_SIGNATURE,
        "name": user.get_full_name() or user.get_username(),
        "job_title": (profile.job_title or "") if profile else "",
        "department": ", ".join(str(labels.get(c, c)) for c in codes),
        "email": user.email,
    }


def signature_text(sig):
    lines = [sig["name"], sig["job_title"], "", sig["company"], sig["department"]]
    if sig.get("phone"):
        lines.append(f"tel. {sig['phone']}")
    if sig["email"]:
        lines.append(f"e-mail: {sig['email']}")
    lines += [sig["www"], sig["address"]]
    return "\n".join(line for i, line in enumerate(lines) if line or i == 2)


def _logo_png():
    from django.contrib.staticfiles import finders

    path = finders.find("img/logo_mail.png")
    if not path:
        return b""
    with open(path, "rb") as f:
        return f.read()


def standalone_sheet(paper):
    """The document as one .html file that opens anywhere: inlined CSS and
    the logo as a data: URI (the mail attachment and saved versions)."""
    logo = _logo_png()
    with translation.override(settings.CLIENT_EMAIL_LANGUAGE):
        return render_to_string("admin/zetom/shared/document_standalone.html", {
            **paper,
            "email_css": email_css(),
            "logo_url": f"data:image/png;base64,{base64.b64encode(logo).decode()}" if logo else "",
        })


_EMAIL_CSS = None


def email_css():
    """tokens.css + document_editor.css with every var(--x) replaced by its
    light value: mail clients (Gmail…) don't support CSS custom properties."""
    global _EMAIL_CSS
    if _EMAIL_CSS is None:
        import re

        from django.contrib.staticfiles import finders

        def read(name):
            path = finders.find(name)
            return open(path, encoding="utf-8").read() if path else ""

        tokens = read("css/tokens.css")
        root = tokens[tokens.find(":root"):]
        root = root[:root.find("}")]
        values = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", root))

        def resolve(match):
            name, fallback = match.group(1), match.group(2)
            value = values.get(name, fallback or "")
            return resolve_all(value.strip())

        def resolve_all(text):
            return re.sub(r"var\((--[\w-]+)(?:\s*,\s*([^()]+))?\)", resolve, text)

        _EMAIL_CSS = resolve_all(read("zetom/css/document_editor.css"))
    return _EMAIL_CSS


class DocumentWindowMixin:
    change_form_template = "admin/zetom/shared/document_change_form.html"

    def get_form(self, request, obj=None, change=False, **kwargs):
        form_class = super().get_form(request, obj, change=change, **kwargs)
        if obj is None:
            return form_class

        class SourceLoggedForm(form_class):
            def clean(self):
                cleaned = super().clean()
                self.client_changes = [f for f in CLIENT_FIELDS if f in self.changed_data]
                if self.client_changes and not (self.data.get("source_channel") or "").strip():
                    raise forms.ValidationError(
                        _("Client data changed — say where the new data came from (contact log)."),
                        code="source_required",
                    )
                return cleaned

        return SourceLoggedForm

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        changes = getattr(form, "client_changes", None)
        if change and changes:
            obj = form.instance
            labels = ", ".join(str(capfirst(obj._meta.get_field(f).verbose_name)) for f in changes)
            channel = request.POST.get("source_channel", "")
            StepNote.objects.create(
                author=request.user,
                kind=StepNote.Kind.CONTACT,
                channel=channel if channel in StepNote.Channel.values else StepNote.Channel.OTHER,
                contacted_at=timezone.now(),
                contact_person=(request.POST.get("source_person") or "").strip()[:255],
                action=str(_("Client data changed: %(fields)s") % {"fields": labels})[:255],
                text=(request.POST.get("source_note") or "").strip(),
                target_content_type=ContentType.objects.get_for_model(type(obj)),
                target_object_id=obj.pk,
            )
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
            path("<path:object_id>/send-to-client/", wrap(self.send_to_client_action), name=f"{prefix}_send_to_client"),
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
        html = standalone_sheet(paper)
        version = sum(
            1 for a in self._files(obj) if a.file.name.rsplit("/", 1)[-1].startswith(slugify(paper["doc_code"]))
        ) + 1
        name = f"{slugify(paper['doc_code'])}-v{version}.html"
        RequestAttachment.objects.create(
            **{self._fk_name(): obj}, file=ContentFile(html.encode("utf-8"), name=name), uploaded_by=request.user,
        )
        messages.success(request, _("Document saved to files: %(name)s") % {"name": name})
        return redirect(self._change_url(obj) + "#files")

    def send_to_client_action(self, request, object_id):
        """Email the finished document to the client: the sheet in the mail
        body + the same sheet as an .html file. Then: status -> waiting
        (sent, waiting for the client), a copy of what was sent in the files,
        an entry in the work log."""
        from crm.notification.services import mail_service
        from crm.status_manager.services.status_service import (
            handle_child_change,
        )
        from crm.status_manager.services.statuses import Status
        from crm.users.utils import user_has_perm
        from crm.zetom.services.reminder_targets import client_email_choices

        if request.method != "POST":
            return redirect(self._change_url(object_id))
        obj, allowed = self._get_doc(request, object_id, change=True)
        if not allowed or not user_has_perm(request.user, "send_documents"):
            return HttpResponseForbidden(_("You don't have permission for this action."))

        to = (request.POST.get("to") or "").strip()
        subject = (request.POST.get("subject") or "").strip()
        message = (request.POST.get("message") or "").strip()
        # claude — known client addresses are suggested, any valid one may be typed
        try:
            validate_email(to)
        except ValidationError:
            messages.error(request, _("Enter a valid email address."))
            return redirect(self._change_url(obj))
        if not subject:
            messages.error(request, _("Subject is required."))
            return redirect(self._change_url(obj))

        paper = document_context(obj, request.user)
        sheet_file = standalone_sheet(paper)
        sig = signature(request.user)
        logo = _logo_png()
        attachments = [(f"{slugify(paper['doc_code'])}.html", sheet_file, "text/html")]
        if logo:
            image = MIMEImage(logo, "png")
            image.add_header("Content-ID", "<zetom-logo>")
            image.add_header("Content-Disposition", "inline", filename="zetom.png")
            attachments.append((image,))
        html_body = render_to_string("admin/zetom/shared/document_email.html", {
            "subject": subject, "message": message, "signature": sig, "logo_cid": "zetom-logo" if logo else "",
        })
        records = mail_service.send_to_client(
            to=to, subject=subject, body=f"{message}\n\n--\n{signature_text(sig)}", html_body=html_body,
            attachments=attachments,
            template_name="admin/zetom/shared/document_email.html",
            payload={"document_id": obj.pk, "document_kind": type(obj).__name__},
            actor=request.user,
        )
        if not any(r.status == "SENT" for r in records):
            messages.error(request, _("The email could not be sent — see the email log."))
            return redirect(self._change_url(obj))

        # status: sent to the client, waiting for an answer (the FSM only
        # allows new -> in_progress -> waiting, so walk it; no "in progress"
        # auto-mail on the way — the client is getting the document itself).
        obj._skip_in_progress_mail = True
        if obj.status == Status.new:
            handle_child_change(obj, Status.in_progress, reason=None, user=request.user)
        if obj.status == Status.in_progress:
            handle_child_change(obj, Status.waiting, reason=None, user=request.user)

        stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
        RequestAttachment.objects.create(
            **{self._fk_name(): obj},
            file=ContentFile(sheet_file.encode("utf-8"), name=f"{slugify(paper['doc_code'])}-wyslane-{stamp}.html"),
            uploaded_by=request.user,
        )
        StepNote.objects.create(
            author=request.user, kind=StepNote.Kind.CONTACT, channel=StepNote.Channel.EMAIL,
            contacted_at=timezone.now(), contact_person=to,
            action=str(_("Document sent to the client: %(subject)s") % {"subject": subject})[:255],
            text=message,
            target_content_type=ContentType.objects.get_for_model(type(obj)), target_object_id=obj.pk,
        )
        messages.success(request, _("Sent to %(email)s. Status: waiting for the client.") % {"email": to})
        return redirect(self._change_url(obj))

    def response_change(self, request, obj):
        # claude — "Send to client" with unsaved edits saves first
        # (document_editor.js sets _open_send) and comes back with the send
        # dialog open, so the client always gets what is on the screen.
        response = super().response_change(request, obj)
        if request.POST.get("_open_send") and response.status_code == 302:
            response["Location"] = response["Location"].split("#")[0] + "#send"
        return response

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
            "client_fields": CLIENT_FIELDS,
            "send_url": reverse(f"{prefix}_send_to_client", args=[obj.pk]),
            "client_emails": client_email_choices(obj),
            "send_subject": _send_subject(obj, paper),
            "send_message": _send_message(obj, paper),
            "can_send": can_change and user_has_perm(request.user, "send_documents"),
            "source_channels": StepNote.Channel.choices,
        }
