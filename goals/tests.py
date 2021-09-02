from goals.factories import GroupFactory
from goals.services import create_monthly_goal
from django.test import TestCase

# Create your tests here.
class GoalTest(TestCase):
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
