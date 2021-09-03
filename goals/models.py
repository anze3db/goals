from django.db import models
from django.utils.translation import gettext_lazy as _

from users.models import User


class Board(models.Model):
    name = models.TextField()

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="boards")
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
    date_deleted = models.DateTimeField(auto_now=True)


class Group(models.Model):
    name = models.TextField()
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="groups")
    color = models.CharField(max_length=255)

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="goal_groups")
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
    date_deleted = models.DateTimeField(auto_now=True)


class Goal(models.Model):
    name = models.TextField()
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="goals")

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="goals")
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
    date_deleted = models.DateTimeField(auto_now=True)


class Result(models.Model):
    name = models.TextField()
    amount = models.FloatField(default=None, null=True)
    expected_amount = models.FloatField(default=0, null=True)
    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="results")


class Event(models.Model):
    description = models.TextField()
    change_amount = models.FloatField(null=True)
    result = models.ForeignKey(Result, on_delete=models.CASCADE, related_name="events")

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="events")
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
