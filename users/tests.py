from django.contrib import auth
from django.test import TestCase
from django.urls import reverse
from model_bakery import baker

from users.models import User


class LoginTest(TestCase):
    def test_login_page(self):
        response = self.client.get("/login")
        self.assertContains(response, "Username")
        self.assertContains(response, "Password")
        self.assertContains(response, "Log in")

    def test_invalid_login(self):
        response = self.client.post("/login", {})
        self.assertContains(response, "Invalid login", status_code=400)

    def test_valid_login(self):
        user = baker.make(User, username="Oliver")
        user.set_password("tart")
        user.save()
        response = self.client.post("/login", {"username": "Oliver", "password": "tart"})
        self.assertRedirects(response, "/")
        self.assertTrue(auth.get_user(self.client).is_authenticated)

    def test_login_never_redirects_to_another_site(self):
        user = baker.make(User, username="Oliver")
        user.set_password("tart")
        user.save()
        response = self.client.post("/login", {"username": "Oliver", "password": "tart", "next": "https://evil.example/"})
        self.assertRedirects(response, "/")


class LogoutTest(TestCase):
    def test_logout_not_logged_in(self):
        self.client.get("/logout")
        self.assertFalse(auth.get_user(self.client).is_authenticated)

    def test_logout(self):
        self.client.force_login(baker.make(User))
        response = self.client.get("/logout")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(auth.get_user(self.client).is_authenticated)


class SettingsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make(User, username="setty")

    def test_requires_login(self):
        response = self.client.get("/settings/")
        self.assertRedirects(response, "/login?next=/settings/", fetch_redirect_response=False)

    def test_settings_page(self):
        self.client.force_login(self.user)
        response = self.client.get("/settings/")
        self.assertContains(response, "Public year report")
        self.assertContains(response, "/u/setty/")

    def test_toggle_public_report(self):
        self.client.force_login(self.user)
        self.assertRedirects(self.client.post("/settings/", {"public_report": "on"}), reverse("settings"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.public_report)

        self.client.post("/settings/", {})
        self.user.refresh_from_db()
        self.assertFalse(self.user.public_report)
