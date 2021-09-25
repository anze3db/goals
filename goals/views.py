from calendar import month_abbr
from django.utils import timezone

from django.contrib.auth.decorators import login_required
from django.http import QueryDict
from django.http.response import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.utils.html import escape
from django.views import View
from django.views.decorators.http import require_GET

from goals.models import Board, Event, Goal, Group, Result
from goals.services import create_monthly_goal
from users.models import User


def _get_table_data(user: User, board: Board):
    boards = user.boards.all()
    months = month_abbr
    groups = board.groups.prefetch_related("goals", "goals__results").all()

    return dict(
        user=user,
        boards=boards,
        months=months,
        groups=groups,
        selected_result=0,
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
    old_amount = result.amount
    result.amount = float(data.get("amount")) or None
    result.expected_amount = float(data.get("expected_amount")) or None
    result.save()

    Event.objects.create(
        user=request.user,
        old_amount=old_amount,
        new_amount=result.amount,
        result=result,
    )

    return render(
        request,
        "table.html",
        _get_table_data(request.user, result.goal.group.board)
        | dict(selected_result=pk),
    )


@login_required(login_url="/login")
def event_post(request, pk):
    data = request.POST
    event = get_object_or_404(Event.objects, pk=pk)

    event.description = data.get("description")
    event.save()

    return HttpResponse("ok")
