# claude
"""RequestMain change page after the declutter redesign: actions are small
header buttons, history opens in a modal, departments sit in the team card."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from crm.zetom.models import RequestMain

User = get_user_model()

DOC = {
    "first_name": "Jan", "last_name": "Kowalski", "phone": "+48501600300",
    "email": "jan@client.pl", "company_name": "Acme", "departments": ["DEPARTMENT_0"],
}


class RequestMainLayoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("boss", "b@zetom.pl", "x")
        self.req = RequestMain.objects.create(**DOC)
        self.client.force_login(self.user)
        self.html = self.client.get(reverse("admin:zetom_requestmain_change", args=[self.req.pk])).content.decode()

    def test_toolbar_in_header(self):
        header = self.html[self.html.index('<header class="rm-header">'):self.html.index("</header>", self.html.index('<header class="rm-header">'))]
        for label in ("rm-toolbar", "open-step-notes", "historyOpen = true", "openReview()", "openMail()", "/cancel/"):
            self.assertIn(label, header)
        self.assertIn('form="requestmain_form" name="_continue"', header)

    def test_old_cards_gone(self):
        self.assertNotIn('id="rm-actions-heading"', self.html)
        self.assertNotIn('id="rm-dept-heading"', self.html)  # departments card
        self.assertIn('class="rm-team-depts"', self.html)    # now inside the team card
        self.assertIn("historyOpen", self.html)
        self.assertNotIn('id="submit-row"', self.html)       # bottom save row only on add

    def test_add_page_keeps_submit_row(self):
        html = self.client.get(reverse("admin:zetom_requestmain_add")).content.decode()
        self.assertIn('id="submit-row"', html)
        self.assertNotIn("rm-toolbar", html)

    def test_save_from_header_button_still_works(self):
        response = self.client.post(
            reverse("admin:zetom_requestmain_change", args=[self.req.pk]),
            {
                "first_name": "Jan", "last_name": "Nowak", "phone": "+48501600300", "email": "jan@client.pl",
                "company_name": "Acme", "company_nip": "", "address": "", "message": "", "source": self.req.source,
                "_continue": "1",
            },
        )
        self.assertEqual(response.status_code, 302, response.context and response.context["adminform"].form.errors)
        self.req.refresh_from_db()
        self.assertEqual(self.req.last_name, "Nowak")
