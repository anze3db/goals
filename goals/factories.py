import factory

from goals.models import Board, Group
from users.factories import UserFactory


class BoardFactory(factory.django.DjangoModelFactory):
    name = factory.Sequence(lambda n: f"{n + 2020} Goals")
    user = factory.SubFactory(UserFactory)

    class Meta:
        model = Board


class GroupFactory(factory.django.DjangoModelFactory):
    name = factory.Faker("name")
    board = factory.SubFactory(BoardFactory, user=factory.SelfAttribute("..user"))
    color = "#000"
    user = factory.SubFactory(UserFactory)

    class Meta:
        model = Group
