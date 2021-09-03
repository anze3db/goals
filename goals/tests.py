from typing import ClassVar

from django.test import TestCase

from goals.factories import BoardFactory, GroupFactory
from goals.models import Group
from goals.services import create_monthly_goal
from users.factories import UserFactory


# Create your tests here.
class GoalTest(TestCase):
    group: ClassVar[Group]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.group = GroupFactory.create()

    def test_monthly_goal_creation(self):
        with self.assertNumQueries(5):
            goal = create_monthly_goal("My Monthly Goal", self.group, self.group.user)
        assert goal
        assert goal.results.count() == 12
        for result in goal.results.all():
            assert result.events.count() == 1


class GoalViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory()
        BoardFactory(user=cls.user)

    def test_index(self):
        self.client.force_login(self.user)
        response = self.client.get("/boards")
        assert response.status_code == 200
