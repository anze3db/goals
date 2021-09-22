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
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

import goals.views
import index.views
import users.views

urlpatterns = [
    path("", index.views.index_view),
    # Goals app
    path("boards", goals.views.BoardsView.as_view()),
    path("boards/<int:pk>", goals.views.BoardsView.as_view()),
    path("boards/add", goals.views.create_board_view),
    path("groups", goals.views.GroupsView.as_view()),
    path("groups/<int:pk>/", goals.views.GroupsView.as_view()),
    path("goals", goals.views.goal_view),
    path("goals/<int:pk>", goals.views.goal_delete_view),
    path("results/<int:pk>", goals.views.result_put),
    path("events/<int:pk>", goals.views.event_post),
    # User app
    path("login", users.views.login),
    # Admin
    path("admin/", admin.site.urls),
]  # + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
