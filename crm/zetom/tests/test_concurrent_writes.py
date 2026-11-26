# claude — real parallel writes against Postgres: N threads (own DB
# connections) add different departments to the same request at the same
# moment. Without the row lock in add_department_action the read-modify-
# write of the ArrayField lost most of them.
import threading

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse

from crm.zetom.models import Department, RequestMain

_SIMPLE_STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
THREADS = 12


@override_settings(STORAGES=_SIMPLE_STATIC)
class ParallelDepartmentAddTests(TransactionTestCase):
    def test_parallel_adds_are_all_kept(self):
        user = get_user_model().objects.create_superuser("admin", "a@a.pl", "x")
        main = RequestMain.objects.create(phone="+48501600300", email="a@b.pl")
        codes = [Department.objects.create(name=f"Lab {i}").code for i in range(THREADS)]
        url = reverse("admin:zetom_requestmain_add_department", args=[main.pk])
        barrier = threading.Barrier(THREADS)
        errors = []

        def worker(code):
            try:
                client = Client()
                client.force_login(user)
                barrier.wait()
                r = client.post(url, {"dept_code": code})
                if r.status_code != 302:
                    errors.append(r.status_code)
            except Exception as exc:  # noqa: BLE001 — reported below
                errors.append(repr(exc))
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(c,)) for c in codes]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        self.assertEqual(errors, [])
        main.refresh_from_db()
        self.assertCountEqual(main.departments, codes)
