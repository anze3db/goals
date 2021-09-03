import uuid

import factory

from .models import User


class UserFactory(factory.django.DjangoModelFactory):
    username = factory.LazyFunction(lambda: f"test+{uuid.uuid4().hex}@example.com")
    email = factory.LazyAttribute(lambda u: u.username)
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")

    class Meta:
        model = User
