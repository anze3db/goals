from users.factories import UserFactory
from goals.factories import BoardFactory
from django.test import TestCase


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
