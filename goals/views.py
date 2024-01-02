from django import forms
from django.contrib.auth.decorators import login_required
from django.http.response import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.decorators import method_decorator
from django.utils.html import escape
from django.views import View

from goals.forms import BoardForm, GoalForm
from goals.models import MONTHS, Board, Event, Group, Result
from goals.services import create_board, create_monthly_goal, update_result
from users.models import User


def _get_table_data(user: User, board: Board, result: Result | None = None):
    boards = user.boards.all()
    groups = board.groups.prefetch_related("goals", "goals__results").all()

    return dict(
        user=user,
        boards=boards,
        months=MONTHS,
        groups=groups,
        board=board,
        selected_result=result,
    )


@method_decorator(login_required(login_url="/login"), name="dispatch")
class BoardsView(View):
    def post(self, request):
        name = request.POST.get("name")
        safe_name = escape(name)
        board = Board.objects.create(name=safe_name, user=request.user)
        Group.objects.create(board=board, user=request.user, name="Default", color="#323")
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
                "month.html",
                _get_table_data(user, board),
            )

        # If pk is not set then redirect to the default one
        if user.default_board:
            return redirect(f"/boards/{user.default_board.pk}/month/{timezone.now().month}")

        return redirect("/boards/add")


@login_required(login_url="/login")
def add_board_view(request):
    if request.method == "GET":
        form = BoardForm()
        return render(request, "board_form.html", {"form": form, "fields_loop": range(15)})

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

        return render(request, "board_form.html", {"form": form})


@login_required(login_url="/login")
def board_month_view(request, board_id, month):
    user = request.user
    board = get_object_or_404(user.boards, pk=board_id)

    boards = user.boards.all()

    return render(
        request,
        "month.html",
        _get_table_data(request.user, board)
        | {
            "boards": boards,
            "user": user,
            "board": board,
            "months": MONTHS,
            "month_index": month,
            "month": [m for m in MONTHS if m.index == month][0],
        },
    )


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
        group, _ = Group.objects.get_or_create(name=form.data.get("group"), board=board, defaults=dict(user=user))
        create_monthly_goal(
            name=form.data.get("name"),
            expected_amount=form.data.get("amount"),
            group=group,
            user=user,
        )
        return HttpResponseRedirect(f"/boards/{board.pk}")

    return render(request, "goal_form.html", {"form": form, "board": board})


@login_required(login_url="/login")
def result_put(request, pk):
    result = get_object_or_404(Result.objects, pk=pk)
    if request.method == "GET":
        events = Event.objects.filter(result__goal=result.goal).order_by("date_event")
        return render(request, "form.html", dict(result=result, events=events))

    data = request.POST
    amount = float(data.get("amount")) if data.get("amount") else None
    expected_amount = float(data.get("expected_amount")) if data.get("expected_amount") else None

    date_event = parse_datetime(data.get("date_event")) or timezone.now()

    update_result(
        result=result,
        amount=amount,
        expected_amount=expected_amount,
        date_event=date_event,
        user=request.user,
        description=data.get("description", ""),
    )

    return redirect(reverse("board_month", args=[result.goal.group.board_id, result.index]))


@login_required(login_url="/login")
def events(request):
    event_objs = Event.objects.filter(user=request.user)
    return render(
        request,
        "events.html",
        {"events": event_objs},
    )


@login_required(login_url="/login")
def event(request, event_id):
    event_obj = get_object_or_404(Event, pk=event_id, user=request.user)
    if request.method == "POST":
        event_obj.description = request.POST.get("description")
        event_obj.save()
        return redirect(reverse("results", args=[event_obj.result_id]))
    return render(
        request,
        "event.html",
        {"event": event_obj},
    )
