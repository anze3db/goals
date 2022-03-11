from datetime import datetime

from django.db import transaction
from django.utils import timezone

from goals.models import Board, Event, Goal, Group, Result
from users.models import User


@transaction.atomic
def create_board(
    user: User, name: str, goals: list[str], groups: list[str], amounts: list[float]
):
    board = Board.objects.create(
        name=name,
        user=user,
    )
    if not user.default_board:
        user.default_board = board
        user.save()

    group_models = create_groups(groups, board, user)
    created_groups = Group.objects.bulk_create(group_models, batch_size=100)
    group_models_map = {g.name: g for g in created_groups}
    for goal_name, group_name, expected_amount in zip(goals, groups, amounts):
        group_model = group_models_map[group_name]
        create_monthly_goal(
            name=goal_name,
            expected_amount=expected_amount,
            group=group_model,
            user=user,
        )
    return board


def create_groups(groups: list[str], board: Board, user: User) -> list[Group]:
    created_groups = set()
    for group in groups:
        if group in created_groups:
            continue
        created_groups.add(group)
        yield Group(name=group, board=board, user=user)


@transaction.atomic
def create_monthly_goal(name: str, expected_amount: float, group: Group, user: User):
    goal = Goal.objects.create(name=name, group=group, user=user)
    current_month = timezone.now().month
    results = [
        Result(
            index=index,
            goal=goal,
            expected_amount=expected_amount if index >= current_month else None,
            amount=0 if index >= current_month else None,
        )
        for index in range(1, 13)
    ]
    events = [
        Event(
            description="Created",
            result=result,
            user=user,
            date_event=timezone.now(),
        )
        for result in results
    ]
    Result.objects.bulk_create(results, batch_size=100)
    Event.objects.bulk_create(events, batch_size=100)
    return goal


@transaction.atomic
def update_result(
    result: Result,
    amount: float | None,
    expected_amount: float | None,
    date_event: datetime,
    user: User,
    description: str = "",
):
    old_amount = result.amount
    result.amount = amount
    result.expected_amount = expected_amount
    result.save()

    Event.objects.create(
        user=user,
        old_amount=old_amount,
        new_amount=result.amount,
        result=result,
        description=description,
        date_event=date_event,
    )


@transaction.atomic
def set_month_amounts():
    Result.objects.filter(
        amount=None, index=datetime.now().month, goal__group__board_id=2
    ).update(amount=0)
