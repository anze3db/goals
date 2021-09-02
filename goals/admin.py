from goals.models import Board, Goal, Group
from django.contrib import admin


admin.site.register(Board, admin.ModelAdmin)
admin.site.register(Group, admin.ModelAdmin)
admin.site.register(Goal, admin.ModelAdmin)
