from django.shortcuts import redirect, render

from users.models import User


def index_view(request):
    if request.user.is_anonymous:
        return render(request, "index.html", dict())

    return redirect("/boards")
