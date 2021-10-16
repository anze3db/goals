from datetime import datetime

from django.db import transaction
from django.utils import timezone

from goals.models import Event, Goal, Group, Result
from users.models import User


@transaction.atomic
def create_monthly_goal(name: str, expected_amount: int, group: Group, user: User):
    goal = Goal.objects.create(name=name, group=group, user=user)
    results = [
        Result(
            index=index,
            goal=goal,
            expected_amount=expected_amount,
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
