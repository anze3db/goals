from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    default_board = models.ForeignKey(
        "goals.Board",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_for_user",
    )
