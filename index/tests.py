from users.factories import UserFactory
from goals.factories import BoardFactory
from django.test import TestCase


class IndexTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory()
        board = BoardFactory(user=cls.user)

    def test_index(self):
        self.client.force_login(self.user)
        self.client.get("/")
