from django.http import HttpRequest

from users.models import User


class AuthenticatedHttpRequest(HttpRequest):
    """For views behind @login_required, so request.user is typed as our User."""

    user: User
