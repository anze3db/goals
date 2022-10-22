from django.contrib import auth
from django.test import TestCase

from .factories import UserFactory


class LoginTest(TestCase):
    def test_login_index(self):
        response = self.client.get("/login")
        assert response.status_code == 200
        response_text = response.content.decode()
        assert "Username" in response_text
        assert "Password" in response_text
        assert "Log in" in response_text

    def test_invalid_login(self):
        response = self.client.post("/login", {})
        assert response.status_code != 200
        response_text = response.content.decode()
        assert "Invalid login" in response_text

    def test_valid_login(self):
        user = UserFactory(username="Oliver")
        user.set_password("tart")
        user.save()
        self.client.post("/login", {"username": "Oliver", "password": "tart"})
        user = auth.get_user(self.client)
        assert user.is_authenticated


class LogoutTest(TestCase):
    def test_logout_not_logged_in(self):
        self.client.get("/logout")
        user = auth.get_user(self.client)
        assert not user.is_authenticated

    def test_logout(self):
        user = UserFactory()
        self.client.force_login(user)
        response = self.client.get("/logout")
        assert response.status_code == 302
        user = auth.get_user(self.client)
        assert not user.is_authenticated
