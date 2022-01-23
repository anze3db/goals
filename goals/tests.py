from typing import ClassVar

from django.test import TestCase
from django.utils import timezone

from goals.factories import (BoardFactory, EventFactory, GroupFactory,
                             ResultFactory)
from goals.models import Board, Goal, Group
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
        for i, result in enumerate(goal.results.all()):
            assert result.events.count() == 1
            assert result.index == i + 1


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
        with self.assertNumQueries(7):
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


class AddBoardViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory()

    def setUp(self):
        self.client.force_login(self.user)

    def test_get(self):
        response = self.client.get("/boards/add")
        assert response.status_code == 200
        assert "Board Name" in response.content.decode()

    def test_post(self):
        response = self.client.post(
            "/boards/add",
            dict(
                name="2021",
                goals=["First Goal", "Second Goal", "Second Personal Goal"],
                groups=["Personal", "Business", "Personal"],
                amounts=["10", "20", "30"],
            ),
        )
        assert response.status_code == 302
        self.user.refresh_from_db()
        board = self.user.default_board
        assert board
        assert board.name == "2021"
        groups = board.groups.all().order_by("name")
        assert [g.name for g in groups] == [
            "Business",
            "Personal",
        ]
        assert [
            ", ".join(group.goals.values_list("name", flat=True)) for group in groups
        ] == [
            "Second Goal",
            "First Goal, Second Personal Goal",
        ]


class ResultsViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.result = ResultFactory(amount=5, expected_amount=10)
        cls.event = EventFactory(result=cls.result)

    def setUp(self):
        self.client.force_login(self.result.goal.user)

    def test_result_get(self):
        with self.assertNumQueries(6):
            response = self.client.get(f"/results/{self.result.pk}")
        assert response.status_code, 200
        result = response.content.decode()
        assert "<form" in result
        assert '<input name="amount" type="number"' in result
        assert '<input name="amount" type="number"' in result
        assert f'value="5.0"' in result
        assert '<input name="expected_amount" type="number"' in result
        assert f'value="10.0"'
        assert "</form>" in result

    def test_result_put(self):
        initial_event_count = self.result.events.count()
        old_amount = self.result.amount
        with self.assertNumQueries(15):
            self.client.post(
                f"/results/{self.result.pk}",
                dict(
                    amount=8,
                    expected_amount=12,
                    date_event="1987-01-01T12:12Z",
                    time_zone="UTC",
                ),
            )

        self.result.refresh_from_db()
        assert self.result.amount == 8.0
        assert self.result.expected_amount == 12.0
        assert self.result.events.count() == initial_event_count + 1
        assert self.result.events.first().new_amount == 8.0
        assert self.result.events.first().old_amount == old_amount
        assert self.result.events.first().date_event == timezone.datetime(
            1987, 1, 1, 12, 12, tzinfo=timezone.utc
        )


class BoardWithResultViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.result = ResultFactory(amount=5, expected_amount=10)

    def setUp(self):
        self.client.force_login(self.result.goal.user)

    def test_result_get(self):
        board = self.result.goal.group.board
        # with self.assertNumQueries(7):
        response = self.client.get(f"/boards/{board.pk}/results/{self.result.pk}")
        assert response.status_code == 200
        # TODO: Add post stuff


class GoalViewTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.board = BoardFactory()

    def setUp(self):
        self.client.force_login(self.board.user)

    def test_form_view(self):
        response = self.client.get(f"/boards/{self.board.pk}/goals/add")
        assert response.status_code == 200
        response_text = response.content.decode()
        assert self.board.name in response_text
        assert '<input name="group"' in response_text
        assert '<input name="name"' in response_text, response_text
        assert '<input name="amount"' in response_text

    def test_form_post(self):
        response = self.client.post(
            f"/boards/{self.board.pk}/goals/add",
            dict(name="my new goal", group="my new group", amount=123),
        )
        assert response.status_code == 302
        Goal.objects.get(
            name="my new goal", group__name="my new group", group__board=self.board
        )

    def test_form_post_existing_group(self):
        group = GroupFactory(board=self.board, name="my new group")
        response = self.client.post(
            f"/boards/{self.board.pk}/goals/add",
            dict(name="my new goal", group="my new group", amount=123),
        )
        assert response.status_code == 302
        goal = Goal.objects.get(
            name="my new goal", group__name="my new group", group__board=self.board
        )
        assert goal.group == group

    def test_invalid_form_post(self):
        response = self.client.post(
            f"/boards/{self.board.pk}/goals/add",
            dict(group="my new group", amount=123),
        )
        assert response.status_code == 200
        response_text = response.content.decode()
        assert "This field is required." in response_text
