from django.contrib import admin
from django.urls import include, path

import goals.views
import users.views

urlpatterns = [
    path("", include("tracker.urls")),
    path("archive/", goals.views.archive, name="archive"),
    path("archive/<int:pk>/", goals.views.archive_board, name="archive_board"),
    path("settings/", users.views.settings, name="settings"),
    path("login", users.views.login_view, name="login"),
    path("logout", users.views.logout_view, name="logout"),
    path("admin/", admin.site.urls),
    # Workers, queues, the daily sync schedule and dead letters. Staff only, like the admin.
    path("ops/potatoq/", include("potatoq.contrib.django.dashboard")),
]
