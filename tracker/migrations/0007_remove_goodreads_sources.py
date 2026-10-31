from django.db import migrations


def remove_goodreads_sources(apps, schema_editor):
    """Goodreads took down its shelf RSS feeds, so the provider is gone.

    Its goals become hand-logged goals that keep the books already synced for their year.
    """
    Activity = apps.get_model("tracker", "Activity")
    Source = apps.get_model("tracker", "Source")
    for source in Source.objects.filter(kind="goodreads"):
        for goal in source.goals.all():
            books = Activity.objects.filter(source=source, type=goal.activity_type, occurred_at__year=goal.year)
            Activity.objects.bulk_create(
                Activity(
                    user_id=book.user_id,
                    goal=goal,
                    type="manual",
                    value=book.value,
                    occurred_at=book.occurred_at,
                    title=book.title,
                    url=book.url,
                )
                for book in books
            )
            goal.source = None
            goal.activity_type = ""
            goal.save(update_fields=["source", "activity_type"])
        source.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0006_goal_groups_and_order"),
    ]

    operations = [
        migrations.RunPython(remove_goodreads_sources, migrations.RunPython.noop),
    ]
