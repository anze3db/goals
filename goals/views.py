from dataclasses import dataclass

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from goals.models import MONTHS, Goal, Result
from users.http import AuthenticatedHttpRequest


@dataclass
class Cell:
    amount: float | None
    expected: float | None
    status: str


@dataclass
class Row:
    name: str
    cells: list[Cell]
    total: float
    expected_total: float
    met: bool


def _cell(result: Result | None) -> Cell:
    if result is None or (result.amount is None and not result.expected_amount):
        return Cell(None, None, "empty")
    if not result.expected_amount:
        return Cell(result.amount, None, "plain")
    met = (result.amount or 0) >= result.expected_amount
    return Cell(result.amount, result.expected_amount, "met" if met else "missed")


def _row(goal: Goal) -> Row:
    by_month = {result.index: result for result in goal.results.all()}
    total = goal.result_sum()
    expected_total = goal.expected_sum()
    return Row(
        name=goal.name,
        cells=[_cell(by_month.get(month.index)) for month in MONTHS],
        total=total,
        expected_total=expected_total,
        met=bool(expected_total) and total >= expected_total,
    )


@login_required
def archive(request: AuthenticatedHttpRequest) -> HttpResponse:
    return render(request, "archive/list.html", {"boards": request.user.boards.all(), "nav": "archive"})


@login_required
def archive_board(request: AuthenticatedHttpRequest, pk: int) -> HttpResponse:
    board = get_object_or_404(request.user.boards, pk=pk)
    groups = [(group.name, [_row(goal) for goal in group.goals.all()]) for group in board.groups.prefetch_related("goals__results")]
    return render(
        request,
        "archive/board.html",
        {"board": board, "groups": groups, "months": MONTHS, "boards": request.user.boards.all(), "nav": "archive"},
    )
