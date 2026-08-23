# claude — регрессия на баг «Deleting the user would result in deleting
# related objects, but your account doesn't have permission»: NotificationAdmin
# и LogEntryAdmin запрещают удаление всем (append-only аудит), а Django
# спрашивает их разрешения при сборе каскада, поэтому удаление юзера было
# заблокировано даже у суперюзера. Плюс основной сценарий, который этот баг
# и должен был закрывать — soft-delete через деактивацию.
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from crm.notification.models import Notification, NotificationKind
from crm.users.models import Permission, TrustedDevice
from crm.users.services.deactivation import deactivate_user, reactivate_user


def _grant(user, *codes):
    profile = user.profile
    profile.role = None
    profile.otp_exempt = True
    profile.save()
    profile.extra_permissions.set(Permission.objects.filter(code__in=codes))


class DeactivationServiceTest(TestCase):
    def setUp(self):
        self.actor = User.objects.create_superuser("root", "root@zetom.pl", "pass12345")
        self.target = User.objects.create_user(
            "worker", "worker@zetom.pl", "pass12345", is_staff=True,
        )
        self.target.profile.otp_exempt = True
        self.target.profile.save()

    def test_deactivate_blocks_login(self):
        deactivate_user(self.target, actor=self.actor)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertFalse(
            self.client.login(username="worker", password="pass12345")
        )

    def test_deactivate_kills_live_session(self):
        self.client.force_login(self.target)
        self.assertTrue(
            Session.objects.filter(expire_date__gte=timezone.now()).exists()
        )

        deactivate_user(self.target, actor=self.actor)

        remaining = [
            s for s in Session.objects.filter(expire_date__gte=timezone.now())
            if s.get_decoded().get("_auth_user_id") == str(self.target.pk)
        ]
        self.assertEqual(remaining, [])

    def test_deactivate_revokes_trusted_devices(self):
        TrustedDevice.objects.create(
            user=self.target,
            token_hash="a" * 64,
            expires_at=timezone.now() + timezone.timedelta(days=30),
        )
        deactivate_user(self.target, actor=self.actor)
        self.assertFalse(TrustedDevice.objects.filter(user=self.target).exists())

    def test_deactivate_writes_log_entry_with_actor(self):
        deactivate_user(self.target, actor=self.actor)
        entry = LogEntry.objects.filter(object_id=str(self.target.pk)).latest("id")
        self.assertEqual(entry.user_id, self.actor.pk)
        self.assertEqual(entry.change_message, "Deactivated")

    def test_deactivate_is_idempotent(self):
        self.assertTrue(deactivate_user(self.target, actor=self.actor))
        before = LogEntry.objects.count()
        self.assertFalse(deactivate_user(self.target, actor=self.actor))
        self.assertEqual(LogEntry.objects.count(), before)

    def test_reactivate_restores_access(self):
        deactivate_user(self.target, actor=self.actor)
        self.assertTrue(reactivate_user(self.target, actor=self.actor))
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertTrue(
            self.client.login(username="worker", password="pass12345")
        )

    def test_reactivate_keeps_role_and_departments(self):
        profile = self.target.profile
        profile.departments = ["quality"]
        profile.save()

        deactivate_user(self.target, actor=self.actor)
        reactivate_user(self.target, actor=self.actor)

        profile.refresh_from_db()
        self.assertEqual(profile.departments, ["quality"])


class DeactivationAdminTest(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            "manager", "manager@zetom.pl", "pass12345", is_staff=True,
        )
        _grant(self.admin_user, "view_users", "edit_users")
        self.target = User.objects.create_user(
            "worker", "worker@zetom.pl", "pass12345", is_staff=True,
        )
        self.target.profile.otp_exempt = True
        self.target.profile.save()
        self.client.force_login(self.admin_user)

    def _action(self, name, pks):
        return self.client.post(
            reverse("admin:auth_user_changelist"),
            {"action": name, "_selected_action": [str(pk) for pk in pks]},
            follow=True,
            HTTP_HOST="127.0.0.1",
        )

    def test_bulk_deactivate(self):
        self._action("deactivate_users", [self.target.pk])
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)

    def test_bulk_reactivate(self):
        deactivate_user(self.target, actor=self.admin_user)
        self._action("reactivate_users", [self.target.pk])
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_cannot_deactivate_self(self):
        self._action("deactivate_users", [self.admin_user.pk])
        self.admin_user.refresh_from_db()
        self.assertTrue(self.admin_user.is_active)

    def test_cannot_deactivate_superuser(self):
        root = User.objects.create_superuser("root", "root@zetom.pl", "pass12345")
        self._action("deactivate_users", [root.pk])
        root.refresh_from_db()
        self.assertTrue(root.is_active)

    # claude — галочка `is_active` на вкладке Permissions обязана давать те же
    # побочные эффекты, что и bulk-action, иначе «выключенный» юзер продолжал
    # бы работать в уже открытой вкладке.
    def test_unchecking_active_in_form_revokes_session(self):
        session_client = self.client_class()
        session_client.force_login(self.target)
        self.assertTrue(
            any(
                s.get_decoded().get("_auth_user_id") == str(self.target.pk)
                for s in Session.objects.all()
            )
        )

        self.client.post(
            reverse("admin:auth_user_change", args=[self.target.pk]),
            {
                "username": self.target.username,
                "email": self.target.email,
                "first_name": "",
                "last_name": "",
                "job_title": "",
                "new_password1": "",
                "new_password2": "",
                # is_active опущен = снятая галочка
            },
            HTTP_HOST="127.0.0.1",
        )

        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertFalse(
            any(
                s.get_decoded().get("_auth_user_id") == str(self.target.pk)
                for s in Session.objects.all()
            )
        )


# claude — кнопка Deactivate/Reactivate на карточке юзера (вкладка Security).
# Отрисовка и эндпоинт ходят через один и тот же _can_toggle_active, поэтому
# каждый кейс проверяется с обеих сторон: видно ли кнопку и пускает ли POST.
class ToggleActiveButtonTest(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            "manager", "manager@zetom.pl", "pass12345", is_staff=True,
        )
        _grant(self.admin_user, "view_users", "edit_users")
        self.target = User.objects.create_user(
            "worker", "worker@zetom.pl", "pass12345", is_staff=True,
        )
        self.target.profile.otp_exempt = True
        self.target.profile.save()
        self.client.force_login(self.admin_user)

    def _toggle_url(self, user):
        return reverse("admin:auth_user_toggle_active", args=[user.pk])

    def _change_page(self, user):
        return self.client.get(
            reverse("admin:auth_user_change", args=[user.pk]),
            {"tab": "security"},
            HTTP_HOST="127.0.0.1",
        )

    def test_button_rendered_for_editable_user(self):
        resp = self._change_page(self.target)
        self.assertTrue(resp.context["can_toggle_active"])
        self.assertContains(resp, self._toggle_url(self.target))

    def test_button_hidden_on_own_card(self):
        resp = self._change_page(self.admin_user)
        self.assertFalse(resp.context["can_toggle_active"])
        self.assertNotContains(resp, self._toggle_url(self.admin_user))

    def test_button_hidden_for_superuser_target(self):
        root = User.objects.create_superuser("root", "root@zetom.pl", "pass12345")
        resp = self._change_page(root)
        self.assertFalse(resp.context["can_toggle_active"])

    def test_post_deactivates(self):
        self.client.post(self._toggle_url(self.target), HTTP_HOST="127.0.0.1")
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)

    def test_post_reactivates_inactive_user(self):
        deactivate_user(self.target, actor=self.admin_user)
        self.client.post(self._toggle_url(self.target), HTTP_HOST="127.0.0.1")
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_post_revokes_session(self):
        session_client = self.client_class()
        session_client.force_login(self.target)

        self.client.post(self._toggle_url(self.target), HTTP_HOST="127.0.0.1")

        self.assertFalse(
            any(
                s.get_decoded().get("_auth_user_id") == str(self.target.pk)
                for s in Session.objects.all()
            )
        )

    def test_post_on_self_is_forbidden(self):
        resp = self.client.post(
            self._toggle_url(self.admin_user), HTTP_HOST="127.0.0.1",
        )
        self.assertEqual(resp.status_code, 403)
        self.admin_user.refresh_from_db()
        self.assertTrue(self.admin_user.is_active)

    def test_post_on_superuser_is_forbidden(self):
        root = User.objects.create_superuser("root", "root@zetom.pl", "pass12345")
        resp = self.client.post(self._toggle_url(root), HTTP_HOST="127.0.0.1")
        self.assertEqual(resp.status_code, 403)
        root.refresh_from_db()
        self.assertTrue(root.is_active)

    def test_post_without_edit_users_is_forbidden(self):
        viewer = User.objects.create_user(
            "viewer", "viewer@zetom.pl", "pass12345", is_staff=True,
        )
        _grant(viewer, "view_users")
        self.client.force_login(viewer)

        resp = self.client.post(self._toggle_url(self.target), HTTP_HOST="127.0.0.1")
        self.assertEqual(resp.status_code, 403)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    # claude — GET ничего не меняет: состояние правится только POST'ом.
    def test_get_does_not_change_state(self):
        self.client.get(self._toggle_url(self.target), HTTP_HOST="127.0.0.1")
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)


class DeletePermissionTest(TestCase):
    def setUp(self):
        self.root = User.objects.create_superuser("root", "root@zetom.pl", "pass12345")
        self.manager = User.objects.create_user(
            "manager", "manager@zetom.pl", "pass12345", is_staff=True,
        )
        _grant(self.manager, "view_users", "edit_users")
        self.target = User.objects.create_user(
            "worker", "worker@zetom.pl", "pass12345", is_staff=True,
        )
        self.target.profile.otp_exempt = True
        self.target.profile.save()

    def _delete_url(self, user):
        return reverse("admin:auth_user_delete", args=[user.pk])

    def test_edit_users_alone_no_longer_grants_delete(self):
        self.client.force_login(self.manager)
        resp = self.client.get(self._delete_url(self.target), HTTP_HOST="127.0.0.1")
        self.assertEqual(resp.status_code, 403)

    def test_superuser_cannot_delete_self(self):
        self.client.force_login(self.root)
        resp = self.client.get(self._delete_url(self.root), HTTP_HOST="127.0.0.1")
        self.assertEqual(resp.status_code, 403)

    # claude — сам баг: у юзера есть Notification и LogEntry, обе админки
    # запрещают удаление, Django собирает их в perms_lacking и прячет кнопку
    # подтверждения. get_deleted_objects снимает эти две модели из проверки.
    def test_superuser_deletes_user_with_notifications_and_logs(self):
        Notification.objects.create(
            recipient=self.target,
            kind=NotificationKind.SYSTEM,
            template_name="dummy",
        )
        LogEntry.objects.create(
            user=self.target,
            content_type=None,
            object_id=str(self.target.pk),
            object_repr=str(self.target),
            action_flag=2,
            change_message="touched something",
        )

        self.client.force_login(self.root)
        resp = self.client.get(self._delete_url(self.target), HTTP_HOST="127.0.0.1")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["perms_lacking"])

        self.client.post(
            self._delete_url(self.target), {"post": "yes"}, HTTP_HOST="127.0.0.1",
        )
        self.assertFalse(User.objects.filter(pk=self.target.pk).exists())
