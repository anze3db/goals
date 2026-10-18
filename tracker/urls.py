from django.urls import path

from tracker import views

urlpatterns = [
    path("", views.index, name="index"),
    path("year/", views.year_view, name="year"),
    path("report/", views.my_report, name="my_report"),
    path("u/<str:username>/<int:year>/", views.report, name="report"),
    path("goals/new/", views.goal_new, name="goal_new"),
    path("goals/<int:pk>/", views.goal_edit, name="goal_edit"),
    path("goals/<int:pk>/delete/", views.goal_delete, name="goal_delete"),
    path("goals/<int:pk>/log/", views.goal_log, name="goal_log"),
    path("sources/", views.sources, name="sources"),
    path("sources/new/<str:kind>/", views.source_new, name="source_new"),
    path("sources/<int:pk>/", views.source_edit, name="source_edit"),
    path("sources/<int:pk>/delete/", views.source_delete, name="source_delete"),
    path("sources/<int:pk>/sync/", views.source_sync, name="source_sync"),
    path("sources/strava/connect/", views.strava_connect, name="strava_connect"),
    path("sources/strava/callback/", views.strava_callback, name="strava_callback"),
    path("in/<str:token>", views.webhook, name="webhook"),
]
