import zipfile
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import IO
from xml.etree import ElementTree

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from tracker.models import Source
from tracker.providers import FetchedActivity
from tracker.providers.base import midday
from tracker.sync import store_activities

STEP_COUNT = "HKQuantityTypeIdentifierStepCount"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S %z"


@contextmanager
def open_export(path: Path):
    """The export.xml inside Health's export.zip, or a bare export.xml."""
    if not zipfile.is_zipfile(path):
        with path.open("rb") as handle:
            yield handle
        return
    with zipfile.ZipFile(path) as archive:
        name = next((n for n in archive.namelist() if n.endswith("/export.xml") or n == "export.xml"), None)
        if name is None:
            raise CommandError(f"No export.xml inside {path}")
        with archive.open(name) as handle:
            yield handle


def daily_steps(handle: IO[bytes], year: int) -> tuple[dict[date, float], int, set[str]]:
    """Sum step records per day and device, then keep each day's busiest device.

    The export holds raw records from every device, so iPhone and Watch both count the same walk.
    The Health app removes that overlap itself; taking the larger device total per day comes close.
    """
    per_device: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    records = 0
    devices: set[str] = set()
    # Full exports run to hundreds of MB: stream them and drop each record from the tree once read
    context = ElementTree.iterparse(handle, events=("start", "end"))
    _, root = next(context)
    for event, element in context:
        if event != "end" or element.tag != "Record":
            continue
        if element.get("type") == STEP_COUNT:
            started = datetime.strptime(element.get("startDate", ""), DATE_FORMAT)
            day = timezone.localtime(started).date()
            if day.year == year:
                device = element.get("sourceName", "")
                per_device[day][device] += float(element.get("value", 0))
                devices.add(device)
                records += 1
        root.clear()
    return {day: max(totals.values()) for day, totals in sorted(per_device.items())}, records, devices


class Command(BaseCommand):
    help = "Import daily step counts from an Apple Health export (Health app → profile → Export All Health Data)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("export", type=Path, help="export.zip, or the export.xml inside it")
        parser.add_argument("--source", required=True, help="Webhook source to store the steps on: its id or name")
        parser.add_argument("--year", type=int, default=timezone.localdate().year)
        parser.add_argument("--type", default="steps", help="Activity type to store, matching your goal (default: steps)")
        parser.add_argument("--dry-run", action="store_true", help="Show what would be imported without saving")

    def handle(self, *args, **options) -> None:
        path: Path = options["export"]
        if not path.exists():
            raise CommandError(f"{path} doesn't exist")
        source = self._source(options["source"])

        with open_export(path) as handle:
            days, records, devices = daily_steps(handle, options["year"])
        if not days:
            raise CommandError(f"No step records for {options['year']} in {path}")

        activity_type = options["type"]
        self.stdout.write(
            f"{records:,} step records from {len(devices)} device(s) ({', '.join(sorted(devices))}): "
            f"{len(days)} days from {min(days)} to {max(days)}, {sum(days.values()):,.0f} steps in total."
        )
        if options["dry_run"]:
            for day, steps in days.items():
                self.stdout.write(f"  {day}  {steps:>8,.0f}")
            self.stdout.write("Dry run: nothing saved.")
            return

        # Same external id as the webhook uses for a dated post, so later Shortcut posts replace these days
        fetched = [
            FetchedActivity(type=activity_type, external_id=f"{activity_type}:{day.isoformat()}", occurred_at=midday(day), value=steps)
            for day, steps in days.items()
        ]
        created = store_activities(source, fetched)
        self.stdout.write(
            self.style.SUCCESS(f"Saved on {source.name}: {created} new days, {len(fetched) - created} already present and replaced.")
        )

    def _source(self, value: str) -> Source:
        sources = Source.objects.filter(kind="webhook")
        matches = list(sources.filter(pk=int(value))) if value.isdigit() else list(sources.filter(name=value))
        if not matches:
            names = ", ".join(f"{s.pk}: {s.name}" for s in sources) or "none"
            raise CommandError(f"No webhook source {value!r}. Webhook sources: {names}")
        if len(matches) > 1:
            raise CommandError(f"Several webhook sources are called {value!r}; pass the id instead")
        return matches[0]
