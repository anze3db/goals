import calendar
from calendar import month_abbr
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.http.response import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.html import escape
from django.views import View

from goals.models import Board, Event, Goal, Group, Result
from goals.services import create_monthly_goal, update_result
from users.models import User


def _get_table_data(user: User, board: Board, result: Result | None = None):
    boards = user.boards.all()
    months = month_abbr
    groups = board.groups.prefetch_related("goals", "goals__results").all()

    return dict(
        user=user,
        boards=boards,
        months=months,
        groups=groups,
        selected_result=result,
        selected_month="" if not result else calendar.month_name[result.index % 12],
    )


@method_decorator(login_required(login_url="/login"), name="dispatch")
class BoardsView(View):
    def post(self, request):
        name = request.POST.get("name")
        safe_name = escape(name)
        board = Board.objects.create(name=safe_name, user=request.user)
        Group.objects.create(
            board=board, user=request.user, name="Default", color="#323"
        )
        r = HttpResponse("ok")
        r.headers["HX-Redirect"] = f"/boards/{board.pk}"
        return r

    def delete(self, request, pk):
        board = get_object_or_404(request.user.boards, pk=pk)
        board.date_deleted = timezone.now()
        board.save()
        # TODO: Update the user's default_board if we just deleted it
        r = HttpResponse("ok")
        r.headers["HX-Redirect"] = "/boards"
        return r

    def get(self, request, pk=None):
        user = request.user
        if pk is not None:
            board = get_object_or_404(user.boards, pk=pk)
            return render(
                request,
                "goals.html",
                _get_table_data(user, board),
            )

        # If pk is not set then redirect to the default one
        if user.default_board:
            return redirect(f"/boards/{user.default_board.pk}")

        return redirect(f"/boards/add")


@login_required(login_url="/login")
def board_with_result_view(request, board_id, result_id):
    user = request.user
    board = get_object_or_404(user.boards, pk=board_id)
    result = get_object_or_404(
        Result.objects, goal__group__board_id=board.pk, pk=result_id
    )
    if data := request.POST:
        amount = float(data.get("amount")) if data.get("amount") else None
        expected_amount = (
            float(data.get("expected_amount")) if data.get("expected_amount") else None
        )
        description = escape(data.get("description"))
        date_event = datetime.fromisoformat(data.get("date_event"))
        update_result(
            result, amount, expected_amount, date_event, request.user, description
        )
        return redirect(f"/boards/{board_id}/results/{result_id}")

    return render(
        request,
        "goals.html",
        _get_table_data(user, board, result),
    )


@login_required(login_url="/login")
def create_board_view(request):
    return HttpResponse("Add board create form here")


@method_decorator(login_required(login_url="/login"), name="dispatch")
class GroupsView(View):
    def post(self, request):
        name = request.POST.get("name")
        board_id = request.POST.get("board_id")
        board = get_object_or_404(Board.objects.all(), pk=board_id)
        safe_name = escape(name)
        Group.objects.create(
            board=board, user=request.user, name=safe_name, color="#323"
        )
        r = HttpResponse("ok")
        r.headers["HX-Redirect"] = f"/boards/{board.pk}"
        return r

    def delete(self, request, pk):
        group = get_object_or_404(Group.objects, pk=pk)
        group.date_deleted = timezone.now()
        group.save()
        r = HttpResponse("ok")
        r.headers["HX-Redirect"] = f"/boards/{group.board.pk}"
        return r


@login_required(login_url="/login")
def goal_view(request):
    user = request.user
    group_id = request.POST.get("group_id")
    name = request.POST.get("name")
    expected_amount = int(request.POST.get("expected_amount"))
    safe_name = escape(name)
    group = get_object_or_404(Group.objects, pk=group_id)
    board = group.board
    create_monthly_goal(safe_name, expected_amount, group, user)
    return render(
        request,
        "table.html",
        _get_table_data(user, board),
    )


@login_required(login_url="/login")
def goal_delete_view(request, pk):
    board = Board.objects.get(groups__goals__pk=pk)
    Goal.objects.filter(pk=pk).delete()

    return render(
        request,
        "table.html",
        _get_table_data(request.user, board),
    )


@login_required(login_url="/login")
def result_put(request, pk):
    if request.method == "GET":
        result = Result.objects.get(pk=pk)
        return render(request, "form.html", dict(result=result))

    data = request.POST
    result = get_object_or_404(Result.objects, pk=pk)
    amount = float(data.get("amount")) if data.get("amount") else None
    expected_amount = (
        float(data.get("expected_amount")) if data.get("expected_amount") else None
    )
    date_event = datetime.fromisoformat(data.get("date_event"))
    update_result(result, amount, expected_amount, date_event, request.user)

    return render(
        request,
        "table.html",
        _get_table_data(request.user, result.goal.group.board)
        | dict(selected_result=result),
    )


@login_required(login_url="/login")
def event_post(request, pk):
    data = request.POST
    event = get_object_or_404(Event.objects, pk=pk)

    event.description = escape(data.get("description"))
    event.save()

    return HttpResponse("ok")
