from django.http.response import HttpResponse


def index_view(request):
    return HttpResponse("ok")
