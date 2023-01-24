from django.contrib import auth
from django.test import TestCase

from goals.factories import BoardFactory

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


class SettingsTest(TestCase):
    def test_settings_page_no_auth(self):
        response = self.client.get("/settings/")
        assert response.status_code == 302
        assert response.url == "/login?next=/settings/"

    def test_settings_page(self):
        user = UserFactory(username="Setty")
        self.client.force_login(user)
        response = self.client.get("/settings/")
        assert response.status_code == 200

    def test_default_board(self):
        user = UserFactory(username="Setty")
        other_user_board = BoardFactory()
        boards = BoardFactory.create_batch(3, user=user)
        board = BoardFactory(user=user)
        user.default_board = board
        user.save()
        self.client.force_login(user)
        response = self.client.get("/settings/")
        assert response.status_code == 200
        response_text = response.content.decode()
        assert f'name="default_board_id"' in response_text
        assert f'value="{board.id}"' in response_text
        assert f"selected>{ board.name }" in response_text
        for b in boards:
            assert f'value="{b.id}"' in response_text
            assert b.name in response_text
        assert f'value="{other_user_board.id}"' not in response_text
        assert other_user_board.name not in response_text

    def test_save_board(self):
        user = UserFactory(username="Setty")
        BoardFactory.create_batch(3, user=user)
        board = BoardFactory(user=user)

        self.client.force_login(user)
        response = self.client.post("/settings/", data=dict(default_board_id=board.id))
        assert response.status_code == 302
        user.refresh_from_db()
        assert user.default_board == board

    def test_save_board_no_change(self):
        user = UserFactory(username="Setty")
        board = BoardFactory(user=user)
        user.default_board = board
        user.save()

        self.client.force_login(user)
        response = self.client.post("/settings/", data=dict(default_board_id=board.id))
        assert response.status_code == 302
        user.refresh_from_db()
        assert user.default_board == board

    def test_save_board_from_other_user(self):
        user = UserFactory(username="Setty")
        board = BoardFactory()

        self.client.force_login(user)
        response = self.client.post("/settings/", data=dict(default_board_id=board.id))
        assert response.status_code == 400
        user.refresh_from_db()
        assert user.default_board is None
