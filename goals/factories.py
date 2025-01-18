import factory
from django.utils import timezone
from faker_optional import OptionalProvider

from goals.models import Board, Event, Goal, Group, Result
from users.factories import UserFactory

factory.Faker.add_provider(OptionalProvider)


class BoardFactory(factory.django.DjangoModelFactory):
    name = factory.Sequence(lambda n: f"{n + 2020}-Goals")
    user = factory.SubFactory(UserFactory)
    boards = factory.RelatedFactoryList(
        "goals.factories.GroupFactory",
        factory_related_name="board",
        size=3,
        user=factory.SelfAttribute("..user"),
    )

    class Meta:
        model = Board
        skip_postgeneration_save = True


class GroupFactory(factory.django.DjangoModelFactory):
    name = factory.Faker("sentence", nb_words=1)
    board = factory.SubFactory(BoardFactory, user=factory.SelfAttribute("..user"))
    color = "#000"
    user = factory.SubFactory(UserFactory)
    goals = factory.RelatedFactoryList(
        "goals.factories.GoalFactory",
        factory_related_name="group",
        size=7,
        user=factory.SelfAttribute("..user"),
    )

    class Meta:
        model = Group
        skip_postgeneration_save = True


class GoalFactory(factory.django.DjangoModelFactory):
    name = factory.Faker("sentence", nb_words=3)
    group = factory.SubFactory(GroupFactory, user=factory.SelfAttribute("..user"))
    user = factory.SubFactory(UserFactory)
    results = factory.RelatedFactoryList(
        "goals.factories.ResultFactory",
        factory_related_name="goal",
        size=3,
    )

    class Meta:
        model = Goal
        skip_postgeneration_save = True


class ResultFactory(factory.django.DjangoModelFactory):
    index = factory.Faker("random_int", min=1, max=12)
    amount = factory.Faker("optional_int", ratio=0.7, min_value=-5, max_value=10)

    expected_amount = factory.Faker("pyint", min_value=0, max_value=15)
    goal = factory.SubFactory(GoalFactory)

    events = factory.RelatedFactoryList(
        "goals.factories.EventFactory",
        factory_related_name="result",
        size=1,
    )

    class Meta:
        model = Result
        skip_postgeneration_save = True


class EventFactory(factory.django.DjangoModelFactory):
    description = factory.Faker("text")

    result = factory.SubFactory(ResultFactory, goal__user=factory.SelfAttribute("...user"))
    user = factory.SubFactory(UserFactory)
    date_event = factory.LazyFunction(timezone.now)

    class Meta:
        model = Event
        skip_postgeneration_save = True
