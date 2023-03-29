"""almograve URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path

import goals.views
import index.views
import users.views

urlpatterns = [
    path("", index.views.index_view, name="index"),
    # Goals app
    path("settings/", users.views.settings, name="settings"),
    path("boards", goals.views.BoardsView.as_view()),
    path("boards/<int:pk>", goals.views.BoardsView.as_view()),
    path("boards/add", goals.views.add_board_view),
    path("boards/<int:board_id>/goals/add", goals.views.add_goal_view),
    path(
        "boards/<int:board_id>/month/<int:month>",
        goals.views.board_month_view,
        name="board_month",
    ),
    path("results/<int:pk>", goals.views.result_put, name="results"),
    path("events/", goals.views.events, name="events"),
    path("events/<int:event_id>", goals.views.event, name="event"),
    # User app
    path("login", users.views.login_view, name="login"),
    path("logout", users.views.logout_view, name="logout"),
    # Admin
    path("admin/", admin.site.urls),
]  # + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
