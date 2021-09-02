from users.models import User
from django.shortcuts import render


def index_view(request):
    user = request.user
    boards = user.boards.all()
    groups = boards.first().groups.all()
    return render(request, "index.html", dict(user=user, boards=boards, groups=groups))
