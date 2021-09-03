from django.contrib import admin

from goals.models import Board, Goal, Group

admin.site.register(Board, admin.ModelAdmin)
admin.site.register(Group, admin.ModelAdmin)
admin.site.register(Goal, admin.ModelAdmin)
