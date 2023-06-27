from calendar import month_abbr
from dataclasses import dataclass
from datetime import datetime

from django.db import models

from users.models import User


class DateDeletedManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(date_deleted__isnull=True)


class Board(models.Model):
    name = models.TextField()

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="boards")
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
    date_deleted = models.DateTimeField(null=True, blank=True)

    objects = DateDeletedManager()

    class Meta:
        ordering = ["date_created"]
        indexes = [models.Index(fields=["date_deleted", "user", "date_created"])]


class Group(models.Model):
    name = models.TextField()
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="groups")
    color = models.CharField(max_length=255)

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="goal_groups")
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
    date_deleted = models.DateTimeField(null=True, blank=True)

    objects = DateDeletedManager()

    class Meta:
        ordering = ["date_created"]
        indexes = [models.Index(fields=["date_deleted", "board", "date_created"])]


class Goal(models.Model):
    name = models.TextField()
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="goals")

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="goals")
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
    date_deleted = models.DateTimeField(null=True, blank=True)

    objects = DateDeletedManager()

    def result_sum(self):
        return sum([r.amount for r in self.results.all() if r.amount])

    def expected_sum(self):
        return sum([r.expected_amount for r in self.results.all() if r.expected_amount])

    def chart_data(self):
        results = self.results.all()
        index_to_amount = {res.index: res.amount for res in results if res.amount}
        index_to_expected = {
            res.index: res.expected_amount for res in results if res.expected_amount
        }

        def get_color(amount, expected_amount):
            if not amount:
                return "gray"
            if amount >= expected_amount:
                return "green"
            return "orange"

        amounts = [index_to_amount.get(index + 1, 0) for index in range(12)]
        colors = [
            get_color(index_to_amount.get(index), index_to_expected.get(index, 0))
            for index in range(12)
        ]
        normalize = [
            (x - min(amounts)) / ((max(amounts) - min(amounts)) or 1) * 0.4 + 0.2
            for x in amounts
        ]
        inverted = [1 - x for x in normalize]
        multipled_by_100 = [x * 100 for x in inverted]
        return {
            "min_amount": min(amounts),
            "max_amount": max(amounts),
            "goal_complete": sum(amounts)
            >= sum(
                [
                    v
                    for i, v in enumerate(index_to_expected.values())
                    if colors[i] != "gray"
                ]
            ),
            "amounts": [
                {
                    "x": (i + 1) * 100,
                    "y": res,
                    "text_y": res - 20,
                    "amount": amounts[i],
                    "color": colors[i],
                    "active": colors[i] != "gray",
                }
                for i, res in enumerate(multipled_by_100)
            ],
            "points": " ".join(
                [
                    f"{(i+1) * 100},{res if colors[i] != 'gray' else 100}"
                    for i, res in enumerate(multipled_by_100)
                ]
            ),
        }

    class Meta:
        ordering = ["date_created"]
        indexes = [models.Index(fields=["date_deleted", "group", "date_created"])]


class Result(models.Model):
    index = models.IntegerField(default=0)
    amount = models.FloatField(default=None, null=True)
    expected_amount = models.FloatField(default=0, null=True)
    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="results")

    class Meta:
        ordering = ["goal", "index"]

    def can_show_amount(self):
        if self.amount:
            # Always True if amount is truthy
            return True
        current_month = datetime.now().month
        return current_month >= self.index

    def month(self):
        return month_abbr[self.index]

    @property
    def next_amount(self) -> float | None:
        if self.amount is None:
            return None
        return self.amount + 1


class Event(models.Model):
    description = models.TextField()
    old_amount = models.IntegerField(null=True)
    new_amount = models.IntegerField(null=True)
    result = models.ForeignKey(Result, on_delete=models.CASCADE, related_name="events")

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="events")
    date_event = models.DateTimeField()
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_created"]

    @property
    def amount(self) -> str:
        if self.new_amount is None:
            return "N/A"

        if self.old_amount is None:
            return f"{self.new_amount}"

        change = self.new_amount - self.old_amount
        if change > 0:
            return f"+{change}"
        return f"{change}"


@dataclass
class Month:
    index: int
    name: str

    @property
    def abbreviation(self):
        return self.name[:3]

    @property
    def initial(self):
        return self.name[0]


MONTHS = [
    Month(1, "January"),
    Month(2, "February"),
    Month(3, "March"),
    Month(4, "April"),
    Month(5, "May"),
    Month(6, "June"),
    Month(7, "July"),
    Month(8, "August"),
    Month(9, "September"),
    Month(10, "October"),
    Month(11, "November"),
    Month(12, "December"),
]
