from django.test import TestCase

from users.factories import UserFactory


class IndexTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory()

    def test_index(self):
        response = self.client.get("/")
        assert response.status_code == 200

    def test_index_logged_in(self):
        self.client.force_login(self.user)
        response = self.client.get("/")
        assert response.status_code == 302
