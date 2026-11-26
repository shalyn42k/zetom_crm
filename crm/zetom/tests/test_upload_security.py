# claude — public form throttle + upload limits (services/throttle.py,
# services/uploads.py) and the sandboxed attachment download (views.py).
import shutil
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from crm.zetom.models import RequestAttachment, RequestMain, RequestNull

_SIMPLE_STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
LEAD = {
    "first_name": "Jan", "last_name": "Kowalski",
    "phone": "+48501600300", "email": "jan@example.pl", "message": "hi",
}


@override_settings(STORAGES=_SIMPLE_STATIC)
@patch("crm.zetom.views.send_notification_to_staff")
class PublicFormLimitsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        self.url = reverse("zetom:index")

    @override_settings(PUBLIC_FORM_RATE_PER_HOUR=2)
    def test_flood_from_one_ip_is_cut_off(self, _mail):
        for _ in range(2):
            self.assertEqual(self.client.post(self.url, LEAD).status_code, 200)
        r = self.client.post(self.url, LEAD)
        self.assertEqual(r.status_code, 429)
        self.assertEqual(RequestNull.objects.count(), 2)

    @override_settings(PUBLIC_FORM_RATE_PER_HOUR=2, TRUST_CF_CONNECTING_IP=True)
    def test_limit_is_per_visitor_behind_cloudflare(self, _mail):
        for ip in ("1.1.1.1", "1.1.1.1", "2.2.2.2"):
            r = self.client.post(self.url, LEAD, HTTP_CF_CONNECTING_IP=ip)
            self.assertEqual(r.status_code, 200)

    @override_settings(PUBLIC_FORM_MAX_FILES=2)
    def test_too_many_files_rejected_before_saving(self, _mail):
        with self.settings(MEDIA_ROOT=self.media):
            files = [SimpleUploadedFile(f"f{i}.txt", b"x") for i in range(3)]
            r = self.client.post(self.url, {**LEAD, "attachments": files})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.context.get("submitted"))
        self.assertEqual(RequestNull.objects.count(), 0)

    @override_settings(MAX_UPLOAD_MB=1)
    def test_too_big_file_rejected(self, _mail):
        with self.settings(MEDIA_ROOT=self.media):
            big = SimpleUploadedFile("big.pdf", b"x" * (1024 * 1024 + 1))
            self.client.post(self.url, {**LEAD, "attachments": [big]})
        self.assertEqual(RequestNull.objects.count(), 0)


@override_settings(STORAGES=_SIMPLE_STATIC)
class AttachmentDownloadSandboxTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        user = get_user_model().objects.create_superuser("admin", "a@a.pl", "x")
        self.client.force_login(user)
        self.main = RequestMain.objects.create(phone="+48501600300", email="a@b.pl")

    def _download(self, name, body):
        with self.settings(MEDIA_ROOT=self.media):
            att = RequestAttachment.objects.create(
                request_main=self.main, file=SimpleUploadedFile(name, body),
            )
            r = self.client.get(reverse("zetom:attachment", args=[att.pk]))
            b"".join(r.streaming_content)
        return r

    def test_html_upload_is_sandboxed(self):
        r = self._download("evil.html", b"<script>alert(1)</script>")
        self.assertEqual(r["Content-Security-Policy"], "sandbox")
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")

    def test_pdf_opens_in_the_browser_viewer(self):
        r = self._download("scan.pdf", b"%PDF-1.4")
        self.assertNotIn("Content-Security-Policy", r)
