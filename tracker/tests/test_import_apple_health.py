import tempfile
import zipfile
from io import StringIO
from pathlib import Path

from django.core.management import CommandError, call_command
from django.test import TestCase
from model_bakery import baker

from tracker.models import Activity, Source

EXPORT = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE HealthData [
<!ELEMENT HealthData (ExportDate,Me,(Record|Workout)*)>
<!ATTLIST HealthData locale CDATA #REQUIRED>
]>
<HealthData locale="en_SI">
 <ExportDate value="2026-10-19 09:00:00 +0200"/>
 <Me HKCharacteristicTypeIdentifierDateOfBirth=""/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Anže's iPhone" unit="count" startDate="2026-03-01 08:00:00 +0000" endDate="2026-03-01 08:10:00 +0000" value="1000"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Anže's iPhone" unit="count" startDate="2026-03-01 12:00:00 +0000" endDate="2026-03-01 12:10:00 +0000" value="500"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Anže's Apple Watch" unit="count" startDate="2026-03-01 08:00:00 +0000" endDate="2026-03-01 08:10:00 +0000" value="1200">
  <MetadataEntry key="HKMetadataKeyDevicePlacementSide" value="0"/>
 </Record>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Anže's iPhone" unit="count" startDate="2026-03-02 09:00:00 +0000" endDate="2026-03-02 09:10:00 +0000" value="4321"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Anže's iPhone" unit="count" startDate="2025-12-31 09:00:00 +0000" endDate="2025-12-31 09:10:00 +0000" value="999"/>
 <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Anže's Apple Watch" unit="count/min" startDate="2026-03-01 08:00:00 +0000" endDate="2026-03-01 08:00:00 +0000" value="60"/>
 <Workout workoutActivityType="HKWorkoutActivityTypeSurfingSports" startDate="2026-03-01 07:00:00 +0000" endDate="2026-03-01 08:00:00 +0000"/>
</HealthData>
"""


class ImportAppleHealthTest(TestCase):
    def setUp(self):
        self.source = baker.make(Source, kind="webhook", name="Apple Health")
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.zip_path = self.directory / "export.zip"
        with zipfile.ZipFile(self.zip_path, "w") as archive:
            archive.writestr("apple_health_export/export_cda.xml", "<ClinicalDocument/>")
            archive.writestr("apple_health_export/export.xml", EXPORT)

    def run_import(self, *args: str) -> str:
        out = StringIO()
        call_command("import_apple_health", *args, stdout=out)
        return out.getvalue()

    def steps(self) -> dict[str, float]:
        return dict(Activity.objects.filter(source=self.source).order_by("occurred_at").values_list("external_id", "value"))

    def test_imports_daily_totals_from_the_busiest_device(self):
        output = self.run_import(str(self.zip_path), "--source", "Apple Health", "--year", "2026")
        # March 1st: iPhone 1,500 vs Watch 1,200 for the same walk, not 2,700
        self.assertEqual(self.steps(), {"steps:2026-03-01": 1500, "steps:2026-03-02": 4321})
        self.assertIn("4 step records from 2 device(s)", output)
        self.assertIn("2 days from 2026-03-01 to 2026-03-02, 5,821 steps in total", output)
        self.assertIn("2 new days, 0 already present and replaced", output)
        activity = Activity.objects.get(external_id="steps:2026-03-02")
        self.assertEqual((activity.type, activity.user_id), ("steps", self.source.user_id))

    def test_reimport_and_webhook_posts_replace_days(self):
        baker.make(Activity, source=self.source, user=self.source.user, type="steps", external_id="steps:2026-03-01", value=7)
        output = self.run_import(str(self.zip_path), "--source", str(self.source.pk), "--year", "2026")
        self.assertIn("1 new days, 1 already present and replaced", output)
        self.assertEqual(self.steps()["steps:2026-03-01"], 1500)

    def test_bare_export_xml_and_other_year(self):
        xml_path = self.directory / "export.xml"
        xml_path.write_text(EXPORT)
        self.run_import(str(xml_path), "--source", "Apple Health", "--year", "2025")
        self.assertEqual(self.steps(), {"steps:2025-12-31": 999})

    def test_dry_run_saves_nothing(self):
        output = self.run_import(str(self.zip_path), "--source", "Apple Health", "--year", "2026", "--dry-run")
        self.assertIn("2026-03-02     4,321", output)
        self.assertIn("Dry run: nothing saved.", output)
        self.assertFalse(Activity.objects.exists())

    def test_custom_type(self):
        self.run_import(str(self.zip_path), "--source", "Apple Health", "--year", "2026", "--type", "walk")
        self.assertEqual(set(Activity.objects.values_list("type", flat=True)), {"walk"})

    def test_errors(self):
        with self.assertRaisesMessage(CommandError, "No webhook source 'Strava'. Webhook sources: "):
            self.run_import(str(self.zip_path), "--source", "Strava")
        baker.make(Source, kind="webhook", name="Apple Health")
        with self.assertRaisesMessage(CommandError, "pass the id instead"):
            self.run_import(str(self.zip_path), "--source", "Apple Health")
        with self.assertRaisesMessage(CommandError, "No step records for 2024"):
            self.run_import(str(self.zip_path), "--source", str(self.source.pk), "--year", "2024")
        with self.assertRaisesMessage(CommandError, "doesn't exist"):
            self.run_import(str(self.directory / "missing.zip"), "--source", str(self.source.pk))
        empty_zip = self.directory / "empty.zip"
        with zipfile.ZipFile(empty_zip, "w") as archive:
            archive.writestr("readme.txt", "")
        with self.assertRaisesMessage(CommandError, "No export.xml inside"):
            self.run_import(str(empty_zip), "--source", str(self.source.pk))
