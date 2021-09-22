from django.db import transaction

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
            change_amount=None,
            result=result,
            user=user,
        )
        for result in results
    ]
    Result.objects.bulk_create(results, batch_size=100)
    Event.objects.bulk_create(events, batch_size=100)
    return goal
