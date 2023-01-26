import calendar
from calendar import month_abbr

from django import forms
from django.contrib.auth.decorators import login_required
from django.http.response import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.decorators import method_decorator
from django.utils.html import escape
from django.views import View

from goals.forms import BoardForm, GoalForm
from goals.models import Board, Group, Result
from goals.services import create_board, create_monthly_goal, update_result
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
        board=board,
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
                "table.html",
                _get_table_data(user, board),
            )

        # If pk is not set then redirect to the default one
        if user.default_board:
            return redirect(f"/boards/{user.default_board.pk}")

        return redirect("/boards/add")


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
        date_event = parse_datetime(data.get("date_event")) or timezone.now()

        update_result(
            result, amount, expected_amount, date_event, request.user, description
        )
        return redirect(f"/boards/{board_id}/results/{result_id}")

    return render(
        request,
        "table.html",
        _get_table_data(user, board, result),
    )


@login_required(login_url="/login")
def add_board_view(request):

    if request.method == "GET":
        form = BoardForm()
        return render(
            request, "board_form.html", {"form": form, "fields_loop": range(15)}
        )

    if request.method == "POST":
        # create a form instance and populate it with data from the request:
        form = BoardForm(request.POST)
        # check whether it's valid:
        if form.is_valid():
            goals = []
            groups = []
            amounts = []
            for goal, group, amount in zip(
                request.POST.getlist("goals"),
                request.POST.getlist("groups"),
                request.POST.getlist("amounts"),
            ):
                if not goal and not group and not amount:
                    # Skip where no value was added
                    continue
                if not goal or not group or not group:
                    continue
                    # TODO: Tell the user that the row will not be added
                    # return render(
                    #     request,
                    #     "board_form.html",

                goals.append(forms.CharField().clean(goal))
                groups.append(forms.CharField().clean(group))
                amounts.append(forms.FloatField().clean(amount))

            board = create_board(
                user=request.user,
                name=form.cleaned_data["name"],
                goals=goals,
                groups=groups,
                amounts=amounts,
            )
            return HttpResponseRedirect(f"/boards/{board.pk}")
        else:
            return render(request, "board_form.html", {"form": form})


@login_required(login_url="/login")
def add_goal_view(request, board_id):
    # if this is a POST request we need to process the form data
    user = request.user
    board = get_object_or_404(user.boards, pk=board_id)
    if request.method != "POST":
        form = GoalForm()
        return render(request, "goal_form.html", {"form": form, "board": board})

    # create a form instance and populate it with data from the request:
    form = GoalForm(request.POST)
    # check whether it's valid:
    if form.is_valid():
        group, _ = Group.objects.get_or_create(
            name=form.data.get("group"), board=board, defaults=dict(user=user)
        )
        create_monthly_goal(
            name=form.data.get("name"),
            expected_amount=form.data.get("amount"),
            group=group,
            user=user,
        )
        return HttpResponseRedirect(f"/boards/{board.pk}")
    else:
        return render(request, "goal_form.html", {"form": form, "board": board})


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

    date_event = parse_datetime(data.get("date_event")) or timezone.now()

    update_result(result, amount, expected_amount, date_event, request.user)

    return render(
        request,
        "table.html",
        _get_table_data(request.user, result.goal.group.board)
        | dict(selected_result=result),
    )
