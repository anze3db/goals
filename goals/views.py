from calendar import month_abbr
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.http import QueryDict
from django.http.response import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.utils.html import escape
from django.views import View

from goals.models import Board, Goal, Group, Result
from goals.services import create_monthly_goal
from users.models import User


def _get_table_data(user: User, board: Board):
    boards = user.boards.all()
    groups = board.groups.all()
    months = month_abbr

    return dict(
        user=user,
        boards=boards,
        months=months,
        current_board=board,
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
        board = get_object_or_404(Board.objects, pk=pk)
        board.date_deleted = datetime.now()
        board.save()
        r = HttpResponse("ok")
        r.headers["HX-Redirect"] = "/boards"
        return r

    def get(self, request, pk=None):
        user = request.user
        if pk is not None:
            board = get_object_or_404(user.boards, pk=pk)
        else:
            boards = user.boards.all()
            if not boards:
                # Should probably redirect to the create board page
                board = Board.objects.create(
                    name=str(datetime.now().year), user=request.user
                )
            else:
                board = boards.first()

        return render(
            request,
            "goals.html",
            _get_table_data(user, board),
        )


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
        group.date_deleted = datetime.utcnow()
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


def result_put(request, pk):
    if request.method == "GET":
        result = Result.objects.get(pk=pk)
        return render(request, "form.html", dict(result=result))

    data = QueryDict(request.body)
    result = get_object_or_404(Result.objects, pk=pk)
    result.amount = data.get("amount") or None
    result.expected_amount = data.get("expected_amount") or None
    result.save()

    return render(
        request,
        "table.html",
        _get_table_data(request.user, result.goal.group.board)
        | dict(selected_result=pk),
    )
