from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http.response import HttpResponseRedirect
from django.shortcuts import render


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            # Redirect to a success page.
            return HttpResponseRedirect("/")
        # Return an 'invalid login' error message.
        return render(
            request,
            "login_form.html",
            {"message": "Invalid login"},
            status=400,
        )
    return render(request, "login_form.html")


def logout_view(request):
    logout(request)
    return HttpResponseRedirect("/")


@login_required(login_url="/login")
def settings(request):
    boards = request.user.boards.all()
    if request.method == "POST":
        default_board_id = int(request.POST.get("default_board_id"))
        if request.user.default_board_id != default_board_id:
            for board in boards:
                if board.id == default_board_id:
                    break
            else:
                return render(
                    request,
                    "settings.html",
                    {"message": "Invalid board id", boards: boards},
                    status=400,
                )
            request.user.default_board_id = default_board_id
            request.user.save()
        return HttpResponseRedirect("/")
    return render(request, "settings.html", {"boards": boards})
