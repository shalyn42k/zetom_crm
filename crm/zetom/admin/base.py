"""Shared admin building blocks: forms, mixins, base ModelAdmin.

Imported by every admin submodule. Keep small and dependency-light —
this module is loaded first and shouldn't pull in Crispy / heavy stuff.
"""
from django import forms
from django.contrib import admin, messages
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import display

from crm.clients.models import Client, CompanyPersonLink
from crm.users.utils import user_has_perm
from crm.zetom.models import (
    DepartmentsVariants, Oferta, RequestMain, StepNote, Wniosek, Zlecenie,
)
from crm.zetom.services.step_notes import (
    HISTORY_FILTER, OPEN_REMINDER_FILTER, create_step_note, mark_reminder_done,
)
from crm.zetom.services.visibility import visible_requests_for


class ReasonForm(forms.Form):
    """Single-field reason form used by status-change reason flow
    (cancel / delete / inactive) and by Trash Restore."""
    reason = forms.CharField(
        widget=forms.Textarea,
        label=_("Reason"),
        required=True,
    )


# claude — text перестал быть required=True на уровне формы: обязательность
# теперь зависит от kind (contact/reminder) и проверяется в StepNote.clean()
# через create_step_note()/full_clean(), не здесь.
class StepNoteCreateForm(forms.Form):
    kind = forms.ChoiceField(
        choices=StepNote.Kind.choices,
        initial=StepNote.Kind.CONTACT,
        label=_("Kind"),
    )
    action = forms.CharField(max_length=255, required=False)
    text = forms.CharField(required=False, label=_("Note"))
    channel = forms.ChoiceField(
        choices=[("", "---------"), *StepNote.Channel.choices],
        required=False,
        label=_("Channel"),
    )
    contacted_at = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M"],
        label=_("Contacted at"),
    )
    next_contact_at = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M"],
        label=_("Next client contact at"),
    )
    person = forms.ModelChoiceField(
        queryset=Client.objects.all(),
        required=False,
        label=_("Person"),
    )
    contact_person = forms.CharField(max_length=255, required=False, label=_("Contact person"))


class DepartmentsDisplayMixin:
    """Renders the ArrayField departments as a comma-separated list of
    labels in admin list_display / readonly_fields."""

    @admin.display(description=_("Departments"))
    def display_departments(self, obj):
        labels = dict(DepartmentsVariants.choices)
        return ", ".join(str(labels.get(code, code)) for code in obj.departments) or "—"


class BaseRequestAdmin(DepartmentsDisplayMixin, ModelAdmin):
    """Shared base for RequestNull / RequestMain / Oferta / Zlecenie /
    Wniosek admins. Wires RBAC permissions and visibility filter."""

    # RBAC
    def has_view_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_requests")

    def has_add_permission(self, request):
        return user_has_perm(request.user, "edit_requests")

    def has_change_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_requests")

    def has_delete_permission(self, request, obj=None):
        return user_has_perm(request.user, "delete_requests")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = visible_requests_for(request.user, qs)
        return qs.prefetch_related("assigned_to")

    class Media:
        # claude — Task 12: the shared work-log modal moved onto the clients
        # app's cc-* design system (static/clients/css/company_card.css);
        # the old sn-* stylesheet is gone.
        css = {
            "all": ("clients/css/company_card.css",),
        }

    def get_urls(self):
        urls = super().get_urls()
        opts = self.model._meta
        custom = [
            path(
                "<path:object_id>/step-notes/create/",
                self.admin_site.admin_view(self.step_note_create_action),
                name=f"{opts.app_label}_{opts.model_name}_step_note_create",
            ),
            # claude — Fix-round: spec §5.2's `zetom_stepnote_done`, which the
            # plan dropped. Registered per-model alongside the create endpoint
            # (rather than as one global url) for two reasons: the note has to
            # be scoped to the thread of the document you are looking at, and
            # the spec's gate is "тот же, что у создания заметки на
            # соответствующей поверхности" — which is exactly this admin's
            # has_change_permission, and is only reachable per ModelAdmin.
            path(
                "<path:object_id>/step-notes/<int:note_pk>/done/",
                self.admin_site.admin_view(self.step_note_done_action),
                name=f"{opts.app_label}_{opts.model_name}_step_note_done",
            ),
        ]
        return custom + urls

    def _get_obj_for_step_note(self, request, object_id):
        obj = self.get_queryset(request).filter(pk=object_id).first()
        if obj is None:
            return None, HttpResponseForbidden(_("Request not found."))
        if not self.has_change_permission(request, obj):
            return None, HttpResponseForbidden(_("You don't have permission for this action."))
        return obj, None

    def step_note_create_action(self, request, object_id):
        if request.method != "POST":
            return redirect(self._change_url_for_id(object_id))

        obj, forbidden = self._get_obj_for_step_note(request, object_id)
        if forbidden is not None:
            return forbidden

        form = StepNoteCreateForm(request.POST)
        if not form.is_valid():
            messages.error(request, _("Could not add note. Check note text/date format."))
            return redirect(self._change_url_for_id(object_id))

        # claude — раньше здесь был StepNote.objects.create(...) без kind/
        # contacted_at, что падало IntegrityError на констрейнтах Task 3.
        # Теперь всё создание идёт через create_step_note(), который валидирует
        # через full_clean() до записи в БД.
        try:
            create_step_note(
                author=request.user,
                kind=form.cleaned_data["kind"],
                action=form.cleaned_data["action"],
                text=form.cleaned_data["text"],
                target=obj,
                person=form.cleaned_data["person"],
                contact_person=form.cleaned_data["contact_person"],
                channel=form.cleaned_data["channel"],
                contacted_at=form.cleaned_data["contacted_at"],
                next_contact_at=form.cleaned_data["next_contact_at"],
            )
        except ValidationError as exc:
            messages.error(
                request,
                _("Could not add note: %(error)s") % {"error": "; ".join(exc.messages)},
            )
            return redirect(self._change_url_for_id(object_id))

        messages.success(request, _("Step note added."))
        return redirect(self._change_url_for_id(object_id))

    # claude — Fix-round: "close a reminder" from a document card. The
    # clients-side twin (ClientAdmin.step_note_done_action) scopes the note by
    # `person=client`; a reminder raised on a document card has no person at
    # all, so it scopes by the note's target instead — the note must belong to
    # this document's own thread (_step_note_targets: the RequestMain plus its
    # child docs). Without that check a crafted note_pk would close another
    # customer's reminder, the same hole `person=client` closes over there.
    # No logic of its own beyond the scoping: the transition itself is
    # services/step_notes.mark_reminder_done, shared with the clients side.
    def step_note_done_action(self, request, object_id, note_pk):
        if request.method != "POST":
            return redirect(self._change_url_for_id(object_id))

        obj, forbidden = self._get_obj_for_step_note(request, object_id)
        if forbidden is not None:
            return forbidden

        note = self._thread_note_or_none(obj, note_pk)
        if note is None:
            return HttpResponseForbidden(_("Note not found."))

        try:
            mark_reminder_done(note, request.user)
        except ValidationError as exc:
            messages.error(
                request,
                _("Could not close reminder: %(error)s") % {"error": "; ".join(exc.messages)},
            )
            return redirect(self._change_url_for_id(object_id))

        messages.success(request, _("Reminder closed."))
        return redirect(self._change_url_for_id(object_id))

    # claude — a StepNote is reachable from `obj`'s card only if its generic
    # target is one of the thread's documents. Reuses the very filter the
    # timeline is built from, so "closeable here" and "visible here" can't
    # drift apart.
    def _thread_note_or_none(self, obj, note_pk):
        targets = self._step_note_targets(obj)
        if not targets:
            return None
        filters, _labels = self._step_note_target_filters(targets)
        return StepNote.objects.filter(filters).filter(pk=note_pk).first()

    def _change_url_for_id(self, object_id):
        opts = self.model._meta
        return reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[object_id])

    def _step_note_targets(self, obj):
        """Return objects whose notes belong to one request thread.

        Thread = RequestMain plus all its child docs. For child docs, this
        includes parent RequestMain and sibling children from the same parent.
        """
        if not obj or not obj.pk:
            return []

        request_main = obj if isinstance(obj, RequestMain) else None
        if request_main is None and hasattr(obj, "from_main_id") and obj.from_main_id:
            request_main = obj.from_main

        targets = []
        if request_main is not None:
            targets.append(request_main)
            targets.extend(list(request_main.oferta_set.only("pk", "created_at")))
            targets.extend(list(request_main.zlecenie_set.only("pk", "created_at")))
            targets.extend(list(request_main.wniosek_set.only("pk", "created_at")))
        else:
            targets.append(obj)

        seen = set()
        deduped = []
        for target in targets:
            if target is None or not target.pk:
                continue
            key = (target._meta.label_lower, target.pk)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(target)
        return deduped

    def _step_note_target_label(self, target):
        if isinstance(target, RequestMain):
            return _("Request")
        if isinstance(target, Oferta):
            return _("Offer")
        if isinstance(target, Zlecenie):
            return _("Order")
        if isinstance(target, Wniosek):
            return _("Application")
        return str(target._meta.verbose_name)

    def _step_note_scope_title(self, obj, targets):
        request_main = obj if isinstance(obj, RequestMain) else None
        if request_main is None and hasattr(obj, "from_main"):
            request_main = obj.from_main

        if request_main is not None and request_main.pk:
            return _("Request no. %(pk)s thread") % {"pk": request_main.pk}
        return str(obj)

    # claude — Fix-round: extracted from _step_notes_for_targets so the done
    # endpoint can scope a note by exactly the same rule the timeline uses.
    def _step_note_target_filters(self, targets):
        type_ids = {}
        for model in {target.__class__ for target in targets}:
            type_ids[model] = ContentType.objects.get_for_model(model).pk

        filters = Q()
        labels = {}
        for target in targets:
            ct_id = type_ids[target.__class__]
            filters |= Q(target_content_type_id=ct_id, target_object_id=target.pk)
            labels[(ct_id, target.pk)] = self._step_note_target_label(target)
        return filters, labels

    # claude — Fix-round: history only — contact notes plus *closed* reminders.
    # Open reminders are handed to the modal separately by
    # _open_reminders_for_targets so the document card gets the same
    # "Zaplanowane above Historia" split the Person/Company cards have (spec
    # §5.3; HISTORY_FILTER is shared with those panels). Without the
    # split an open reminder was just another grey line in the log, with
    # nothing to close it.
    def _step_notes_for_targets(self, targets):
        if not targets:
            return []

        filters, labels = self._step_note_target_filters(targets)

        # claude — Fix-round: sort (and render, see the template) on when the
        # contact actually happened, not on when the row was written.
        # created_at is auto_now_add, so every note migrated from
        # ClientInteraction carries the migration's run time — the whole
        # historical log read as "X minutes ago", and a note logged today
        # about last week's call jumped to the top as "now". Coalesce puts the
        # fallback (reminders have no contacted_at) inside the ORDER BY rather
        # than in a Python-side sort. Identical treatment to the Person/Company
        # panels — crm/clients/services_contacts.py::_history_notes — so the
        # two surfaces can't disagree about the same note.
        notes = list(
            StepNote.objects
            .filter(filters)
            .filter(HISTORY_FILTER)
            .select_related("author")
            .annotate(sort_at=Coalesce("contacted_at", "created_at"))
            .order_by("-sort_at")[:100]
        )
        for note in notes:
            note.stage_label = labels.get((note.target_content_type_id, note.target_object_id), "")
            note.is_overdue = False
        return notes

    # claude — Fix-round: the thread's still-open reminders, soonest first.
    # Deliberately NOT sliced like the history above: a thread with a hundred
    # logged calls would otherwise push its one open reminder out of the
    # result and make it unclosable again — the exact bug this fixes. There
    # are only ever a handful of open reminders per thread.
    def _open_reminders_for_targets(self, obj, targets):
        if not targets:
            return []

        opts = self.model._meta
        filters, labels = self._step_note_target_filters(targets)
        reminders = list(
            StepNote.objects
            .filter(filters)
            .filter(OPEN_REMINDER_FILTER)
            .select_related("author")
            .order_by("next_contact_at")
        )
        # claude — Task 12: flag past-due reminders so the template can mark
        # them (.hev.overdue -> red dot). Same is_overdue rule as
        # clients/services_contacts.py's "Zaplanowane" panel. done_url is what
        # makes the checkmark possible on a document card at all — it is
        # addressed by THIS document, not by the note's person (which a
        # document-card reminder does not have).
        now = timezone.now()
        for note in reminders:
            note.stage_label = labels.get((note.target_content_type_id, note.target_object_id), "")
            note.is_overdue = bool(note.next_contact_at and note.next_contact_at < now)
            note.done_url = reverse(
                f"admin:{opts.app_label}_{opts.model_name}_step_note_done",
                args=[obj.pk, note.pk],
            )
        return reminders

    def _build_step_notes_context(self, obj):
        opts = self.model._meta
        if not obj or not obj.pk:
            return {
                "step_notes_enabled": False,
                "step_notes": [],
                "step_notes_open_reminders": [],
                "step_notes_create_url": "",
                "step_notes_target_label": "",
                "step_notes_persons": [],
            }

        targets = self._step_note_targets(obj)
        return {
            "step_notes_enabled": True,
            "step_notes": self._step_notes_for_targets(targets),
            "step_notes_open_reminders": self._open_reminders_for_targets(obj, targets),
            "step_notes_create_url": reverse(
                f"admin:{opts.app_label}_{opts.model_name}_step_note_create",
                args=[obj.pk],
            ),
            "step_notes_target_label": self._step_note_scope_title(obj, targets),
            "step_notes_persons": self._step_note_persons(obj),
        }

    # claude — Task 12: people the "who did you talk to" picker can offer —
    # persons already linked to the request thread (RequestMain.clients)
    # plus persons of its company (RequestMain.company -> CompanyPersonLink),
    # deduplicated. `obj` can be RequestMain itself or a child document, so
    # this resolves to the thread's RequestMain the same way
    # `_step_note_targets` does.
    def _step_note_persons(self, obj):
        request_main = obj if isinstance(obj, RequestMain) else None
        if request_main is None and hasattr(obj, "from_main_id") and obj.from_main_id:
            request_main = obj.from_main
        if request_main is None:
            return []

        persons = list(request_main.clients.all())
        if request_main.company_id:
            persons.extend(
                link.person
                for link in CompanyPersonLink.objects
                .filter(company_id=request_main.company_id)
                .select_related("person")
            )

        seen = set()
        deduped = []
        for person in persons:
            if person.pk in seen:
                continue
            seen.add(person.pk)
            deduped.append(person)
        return deduped

    def render_change_form(self, request, context, *args, **kwargs):
        obj = context.get("original")
        context.update(self._build_step_notes_context(obj))
        return super().render_change_form(request, context, *args, **kwargs)

    # claude — prefills the request's contact snapshot from ?client=<pk>. The
    # clients M2M uses a through-model so it can't be a form field; the snapshot
    # is what the validator would copy anyway.
    #
    # Currently nothing in the UI links here: the entry point was "Create new"
    # on the old Client Detail request tabs, which the Person card replaced.
    # Kept rather than deleted because it is the whole backend for "start a
    # request from this client" — the pending Requests redesign only needs to
    # point a button at `?client=<pk>` to have the feature back.
    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        client_id = request.GET.get("client")
        if client_id:
            from crm.clients.models import Client
            client = Client.objects.filter(pk=client_id).first()
            if client:
                # claude — фирменные поля снапшота берём из связанной Company
                # (company_* уезжают с Client в 2c).
                link = client.company_links.first()
                company = link.company if link else None
                initial.update({
                    "first_name": client.first_name,
                    "last_name": client.last_name,
                    "company_name": company.name if company else "",
                    "company_nip": company.nip if company else "",
                    "phone": client.phone,
                    "email": client.email,
                })
        return initial

    @admin.display(description=_("Assigned"))
    def assignees_display(self, obj):
        users = obj.assigned_to.all()
        return ", ".join(u.username for u in users) or "—"

    @display(
        label={
            "new": "info",
            "in_progress": "warning",
            "waiting": "secondary",
            "done": "success",
        },
        description=_("Status"),
    )
    def colored_status(self, obj):
        from crm.status_manager.services.statuses import Status
        return obj.status, str(Status(obj.status).label) if obj.status in Status.values else obj.status
