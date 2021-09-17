from typing import ClassVar

from django.test import TestCase

from goals.factories import BoardFactory, GroupFactory
from goals.models import Board, Group
from goals.services import create_monthly_goal
from users.factories import UserFactory


class GoalTest(TestCase):
    group: ClassVar[Group]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.group = GroupFactory.create()

    def test_monthly_goal_creation(self):
        with self.assertNumQueries(5):
            goal = create_monthly_goal(
                "My Monthly Goal", 10, self.group, self.group.user
            )
        assert goal
        assert goal.results.count() == 12
        for result in goal.results.all():
            assert result.events.count() == 1


class BoardsViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory()
        cls.board = BoardFactory(user=cls.user)
        cls.board_2 = BoardFactory(user=cls.user)
        cls.another_users_board = BoardFactory()

    def setUp(self) -> None:
        self.client.force_login(self.user)  # type: ignore

    def test_default_board_redirect(self):
        self.user.default_board = self.board
        self.user.save()

        with self.assertNumQueries(3):
            response = self.client.get("/boards")
        self.assertRedirects(response, f"/boards/{self.board.pk}")

    def test_no_default_board(self):
        with self.assertNumQueries(2):
            response = self.client.get("/boards")
        self.assertRedirects(response, f"/boards/add")

    def test_specific_board(self):
        response = self.client.get(f"/boards/{self.board_2.pk}")
        assert response.status_code == 200
        assert self.board_2.name in response.content.decode()
        assert self.board_2.groups.first().name in response.content.decode()
        assert self.board.groups.first().name not in response.content.decode()

    def test_post_board(self):
        response = self.client.post("/boards", {"name": "2022 New Board"})
        assert response.status_code == 200
        assert Board.objects.filter(user=self.user, name="2022 New Board").exists()

    def test_404_page(self):
        response = self.client.get("/boards/0")
        assert response.status_code == 404

    def test_not_logged_in(self):
        self.client.logout()
        response = self.client.get("/boards")
        self.assertRedirects(response, "/login?next=/boards")

    def test_delete_board(self):
        with self.assertNumQueries(4):
            self.client.delete(f"/boards/{self.board.pk}")
        self.board.refresh_from_db()
        assert self.board.date_deleted

    def test_delete_board_from_another_user(self):
        with self.assertNumQueries(3):
            self.client.delete(f"/boards/{self.another_users_board.pk}")
        self.another_users_board.refresh_from_db()
        assert self.another_users_board.date_deleted is None
