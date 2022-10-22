from django.contrib.auth import authenticate, login, logout
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
        else:
            # Return an 'invalid login' error message.
            return render(
                request, "login_form.html", {"message": "Invalid login"}, status=400
            )
    return render(request, "login_form.html")


def logout_view(request):
    logout(request)
    return HttpResponseRedirect("/")
