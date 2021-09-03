from django.shortcuts import redirect, render


def index_view(request):
    if request.user.is_anonymous:
        return render(request, "index.html", {})

    return redirect("/boards")
