from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http.response import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return HttpResponseRedirect("/")
        return render(
            request,
            "users/login.html",
            {"message": "Invalid login"},
            status=400,
        )
    return render(request, "users/login.html")


def logout_view(request):
    logout(request)
    return HttpResponseRedirect("/")


@login_required
def settings(request):
    if request.method == "POST":
        request.user.public_report = request.POST.get("public_report") == "on"
        request.user.save(update_fields=["public_report"])
        return HttpResponseRedirect(reverse("settings"))
    report_url = request.build_absolute_uri(reverse("report", args=[request.user.username, timezone.localdate().year]))
    return render(request, "users/settings.html", {"report_url": report_url, "nav": "settings"})
