from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    # Anyone can see /u/<username>/<year>/ when this is on
    public_report = models.BooleanField(default=False)
    # Only used by the archive of the old monthly boards
    default_board = models.ForeignKey(
        "goals.Board",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_for_user",
    )
