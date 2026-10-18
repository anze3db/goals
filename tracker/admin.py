from django.contrib import admin

from tracker.models import Activity, Goal, Source


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "user", "enabled", "last_synced_at"]
    list_filter = ["kind", "enabled"]
    exclude = ["secrets"]


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ["name", "year", "target", "unit", "source", "activity_type", "aggregation", "user"]
    list_filter = ["year", "aggregation"]


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ["occurred_at", "type", "value", "title", "source", "user"]
    list_filter = ["type", "source"]
    date_hierarchy = "occurred_at"
    search_fields = ["title", "external_id"]
