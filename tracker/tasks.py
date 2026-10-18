from potatoq import shared_task

from tracker.models import Source
from tracker.sync import sync_source


@shared_task
def sync_source_task(source_id: int) -> int:
    source = Source.objects.filter(pk=source_id, enabled=True).first()
    if source is None:
        return 0
    return sync_source(source)


@shared_task
def sync_all_sources() -> int:
    """Runs every 15 minutes (POTATOQ beat_schedule) and fans out one task per source."""
    source_ids = [source.pk for source in Source.objects.filter(enabled=True) if source.provider.pulls]
    for source_id in source_ids:
        sync_source_task.delay(source_id)
    return len(source_ids)
