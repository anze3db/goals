import json
from datetime import date
from typing import Any

from django.test import SimpleTestCase
from model_bakery import baker

from tracker.models import Activity, Goal
from tracker.progress import (
    compute_progress,
    format_number,
    headline,
    month_bars,
    squares,
    year_fraction,
)
from tracker.providers.base import midday

TODAY = date(2026, 7, 2)  # day 183 of 365, almost exactly half the year


def make_goal(**kwargs: Any) -> Goal:
    defaults: dict[str, Any] = {"name": "Run", "year": 2026, "target": 100, "unit": "km", "aggregation": Goal.Aggregation.SUM}
    return baker.prepare(Goal, **(defaults | kwargs))


def activity(day: date, value: float = 1) -> Activity:
    return baker.prepare(Activity, occurred_at=midday(day), value=value)


class YearFractionTest(SimpleTestCase):
    def test_counts_today_as_done(self):
        self.assertEqual(year_fraction(2026, date(2026, 1, 1)), 1 / 365)
        self.assertEqual(year_fraction(2026, date(2026, 12, 31)), 1.0)

    def test_past_and_future_years(self):
        self.assertEqual(year_fraction(2025, TODAY), 1.0)
        self.assertEqual(year_fraction(2027, TODAY), 0.0)


class ComputeProgressTest(SimpleTestCase):
    def test_sum_ahead(self):
        progress = compute_progress(make_goal(), [activity(date(2026, 3, 1), 40), activity(date(2026, 6, 1), 30)], TODAY)
        self.assertEqual(progress.current, 70)
        self.assertEqual(progress.status, "ahead")
        self.assertAlmostEqual(progress.expected, 100 * 183 / 365)
        self.assertAlmostEqual(progress.projected, 70 / (183 / 365))
        self.assertEqual(progress.chip, "+19.9 km ahead")

    def test_sum_behind(self):
        progress = compute_progress(make_goal(), [activity(date(2026, 3, 1), 10)], TODAY)
        self.assertEqual(progress.status, "behind")
        self.assertEqual(progress.chip, "40.1 km behind")

    def test_on_pace_within_tolerance(self):
        progress = compute_progress(make_goal(), [activity(date(2026, 3, 1), 51)], TODAY)
        self.assertEqual(progress.status, "pace")
        self.assertEqual(progress.chip, "On pace")

    def test_done_records_the_day(self):
        progress = compute_progress(make_goal(), [activity(date(2026, 2, 1), 60), activity(date(2026, 4, 5), 60)], TODAY)
        self.assertEqual(progress.status, "done")
        self.assertEqual(progress.completed_on, date(2026, 4, 5))
        self.assertEqual(progress.chip, "Done · +20")
        self.assertEqual(progress.chart.projection, "")

    def test_count_ignores_values(self):
        goal = make_goal(aggregation=Goal.Aggregation.COUNT, target=4)
        progress = compute_progress(goal, [activity(date(2026, 1, 5), 0), activity(date(2026, 1, 5), 12)], TODAY)
        self.assertEqual(progress.current, 2)
        self.assertEqual(progress.daily, {date(2026, 1, 5): 2})

    def test_latest_measures_from_first_reading(self):
        goal = make_goal(aggregation=Goal.Aggregation.LATEST, target=1200, unit="followers")
        readings = [activity(date(2026, 1, 1), 1000), activity(date(2026, 3, 1), 1050), activity(date(2026, 7, 1), 1110)]
        progress = compute_progress(goal, readings, TODAY)
        self.assertEqual(progress.baseline, 1000)
        self.assertEqual(progress.current, 1110)
        self.assertAlmostEqual(progress.expected, 1000 + 200 * 183 / 365)
        self.assertEqual(progress.status, "ahead")
        self.assertAlmostEqual(progress.percent, 55.0)

    def test_no_activity(self):
        progress = compute_progress(make_goal(), [], TODAY)
        self.assertEqual(progress.current, 0)
        self.assertEqual(progress.status, "behind")
        self.assertTrue(progress.chart.actual.startswith("M6.0 104.0"))

    def test_chart_paths(self):
        progress = compute_progress(make_goal(), [activity(date(2026, 3, 1), 40)], TODAY)
        chart = progress.chart
        self.assertTrue(chart.pace.startswith("M6.0 104.0 L314.0"))
        self.assertTrue(chart.area.endswith("Z"))
        self.assertTrue(chart.projection.startswith(f"M{chart.today_x}"))
        self.assertIn("Run: 40 of 100 km", chart.label)

    def test_chart_hover_has_a_row_per_day_so_far(self):
        progress = compute_progress(make_goal(), [activity(date(2026, 3, 1), 40)], TODAY)
        rows = json.loads(progress.chart.hover)
        self.assertEqual(len(rows), 183)
        self.assertEqual(rows[0][2:], ["Thu 1 Jan", "0 / 100 km", "pace 0.3"])
        self.assertEqual(rows[59][2:], ["Sun 1 Mar", "40 / 100 km", "+40 that day · pace 16.4"])
        self.assertEqual(rows[60][3], "40 / 100 km")
        self.assertEqual(rows[-1][0], float(progress.chart.today_x))


class SquaresTest(SimpleTestCase):
    def test_grid_and_streaks(self):
        days = [date(2026, 6, 28), date(2026, 6, 29), date(2026, 7, 1), date(2026, 7, 2), date(2026, 1, 1)]
        progress = compute_progress(make_goal(), [activity(day, 5) for day in days], TODAY)
        result = squares(progress, TODAY)

        # 2026 starts on a Thursday, so the first column has three empty slots
        self.assertEqual([c.css for c in result.weeks[0][:4]], ["out", "out", "out", "l4"])
        self.assertEqual(len(result.weeks), 53)
        self.assertEqual(result.weeks[26][3].css, "l4 today")
        self.assertEqual(result.weeks[26][4].css, "future")
        self.assertEqual((result.weeks[26][3].day, result.weeks[26][3].value), ("Thu 2 Jul", "5 km"))
        self.assertEqual((result.weeks[26][1].day, result.weeks[26][1].value), ("Tue 30 Jun", "Nothing"))
        self.assertEqual(result.weeks[26][4].day, "")
        self.assertEqual(result.streak, 2)
        self.assertEqual(result.best_streak, 2)
        self.assertEqual(result.active_days, 5)
        self.assertEqual(result.month_slots[0], "Jan")
        self.assertEqual(result.month_slots.count(""), 53 - 12)

    def test_streak_survives_an_empty_today(self):
        progress = compute_progress(make_goal(), [activity(date(2026, 6, 30)), activity(date(2026, 7, 1))], TODAY)
        self.assertEqual(squares(progress, TODAY).streak, 2)

    def test_intensity_levels_are_relative(self):
        values = {date(2026, 1, d): v for d, v in [(5, 1), (6, 2), (7, 3), (8, 4)]}
        progress = compute_progress(make_goal(), [activity(day, v) for day, v in values.items()], TODAY)
        week = squares(progress, TODAY).weeks[1]
        self.assertEqual([c.css for c in week[:4]], ["l1", "l2", "l3", "l4"])

    def test_latest_goal_lights_up_days_that_grew(self):
        goal = make_goal(aggregation=Goal.Aggregation.LATEST, target=200)
        readings = [activity(date(2026, 1, 5), 100), activity(date(2026, 1, 6), 100), activity(date(2026, 1, 7), 110)]
        week = squares(compute_progress(goal, readings, TODAY), TODAY).weeks[1]
        self.assertEqual([c.css for c in week[:3]], ["l0", "l0", "l4"])
        self.assertEqual([c.value for c in week[:4]], ["100 km", "100 km", "110 km · +10", "110 km"])


class MonthBarsTest(SimpleTestCase):
    def test_bars(self):
        progress = compute_progress(make_goal(), [activity(date(2026, 1, 3), 10), activity(date(2026, 3, 3), 20)], TODAY)
        bars = month_bars(progress, TODAY, max_height=100)
        self.assertEqual([b.value for b in bars[:4]], [10, 0, 20, 0])
        self.assertEqual(bars[0].height, 50)
        self.assertTrue(bars[2].best)
        self.assertFalse(bars[6].future)
        self.assertTrue(bars[7].future)


class HeadlineTest(SimpleTestCase):
    def test_headline(self):
        ahead = compute_progress(make_goal(), [activity(date(2026, 3, 1), 70)], TODAY)
        behind = compute_progress(make_goal(), [], TODAY)
        self.assertEqual(headline([ahead, behind], 0), "Ahead on one, behind on one. Nothing to log today.")
        self.assertEqual(headline([ahead, ahead], 1), "Ahead on two. One tracked by hand.")
        self.assertEqual(headline([], 0), "No goals yet. Connect a source and add one.")


class FormatNumberTest(SimpleTestCase):
    def test_format(self):
        self.assertEqual(format_number(1234.56), "1,235")
        self.assertEqual(format_number(12.0), "12")
        self.assertEqual(format_number(2.84), "2.8")


class RecurringGoalTest(SimpleTestCase):
    def daily_goal(self, **kwargs: Any) -> Goal:
        return make_goal(**({"name": "Steps", "target": 10_000, "unit": "steps", "period": Goal.Period.DAY} | kwargs))

    def test_daily_target_counts_days_hit_and_streak(self):
        steps = {date(2026, 6, 28): 12_000, date(2026, 6, 29): 3_000, date(2026, 6, 30): 10_000, date(2026, 7, 1): 15_000}
        progress = compute_progress(self.daily_goal(), [activity(day, value) for day, value in steps.items()], TODAY)
        self.assertEqual((progress.hit_count, progress.elapsed_count), (3, 183))
        self.assertEqual((progress.streak, progress.best_streak), (2, 2))
        # Today has no steps yet, but yesterday kept the streak alive
        self.assertEqual(progress.current, 0)
        self.assertEqual(progress.status, "pace")
        self.assertEqual(progress.chip, "2-day streak · 10,000 steps to go")
        self.assertAlmostEqual(progress.percent, 3 / 183 * 100)

    def test_hit_today(self):
        progress = compute_progress(self.daily_goal(), [activity(TODAY, 6_000), activity(TODAY, 5_000)], TODAY)
        self.assertEqual((progress.current, progress.status, progress.chip), (11_000, "done", "Hit today"))

    def test_streak_broken(self):
        progress = compute_progress(self.daily_goal(), [activity(date(2026, 6, 30), 20_000), activity(TODAY, 2_000)], TODAY)
        self.assertEqual((progress.streak, progress.best_streak, progress.status), (0, 1, "behind"))
        self.assertEqual(progress.chip, "8,000 steps to go")

    def test_weekly_periods_are_monday_to_sunday_within_the_year(self):
        goal = make_goal(name="Strength", target=3, unit="sessions", period=Goal.Period.WEEK, aggregation=Goal.Aggregation.COUNT)
        sessions = [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3), date(2026, 6, 22), date(2026, 6, 24), date(2026, 6, 26)]
        progress = compute_progress(goal, [activity(day) for day in sessions], TODAY)
        first = progress.periods[0]
        # 2026 starts on a Thursday, so the first week is Thursday to Sunday
        self.assertEqual((first.start, first.end, first.total, first.hit), (date(2026, 1, 1), date(2026, 1, 4), 3, True))
        self.assertEqual(progress.periods[-1].start, date(2026, 6, 29))
        self.assertTrue(progress.periods[-1].current)
        self.assertEqual((progress.hit_count, progress.streak), (2, 1))
        self.assertEqual(progress.chip, "3 sessions to go")
        self.assertIn("hit 2 of 27 weeks", progress.chart.label)
        rows = json.loads(progress.chart.hover)
        self.assertEqual(rows[1][2:], ["Fri 2 Jan", "3 / 3 sessions", "week of 1 Jan · +1 that day · hit"])
        self.assertEqual(rows[-1][2:], ["Thu 2 Jul", "0 / 3 sessions", "week of 29 Jun"])

    def test_monthly_target(self):
        goal = make_goal(name="Posts", target=2, unit="posts", period=Goal.Period.MONTH, aggregation=Goal.Aggregation.COUNT)
        posts = [date(2026, 5, 3), date(2026, 5, 20), date(2026, 6, 1), date(2026, 6, 9), date(2026, 7, 1), date(2026, 7, 2)]
        progress = compute_progress(goal, [activity(day) for day in posts], TODAY)
        self.assertEqual((progress.elapsed_count, progress.hit_count), (7, 3))
        self.assertEqual((progress.streak, progress.status), (3, "done"))
        self.assertEqual(progress.chip, "Hit this month · 3-month streak")

    def test_finished_year(self):
        progress = compute_progress(self.daily_goal(), [activity(date(2026, 3, 1), 11_000)], date(2027, 2, 1))
        self.assertEqual((progress.elapsed_count, progress.hit_count, progress.status), (365, 1, "behind"))
        self.assertEqual(progress.chip, "Hit 1 of 365")

    def test_bars(self):
        progress = compute_progress(self.daily_goal(), [activity(date(2026, 1, 1), 10_000), activity(date(2026, 1, 2), 5_000)], TODAY)
        chart = progress.chart
        self.assertEqual(chart.hit_bars.count("M"), 1)
        self.assertEqual(chart.miss_bars.count("M"), 182)
        self.assertTrue(chart.hit_bars.startswith("M6.0 104.0 V"))
        self.assertEqual(chart.projection, "")

    def test_squares_shade_by_target_and_count_hits(self):
        values = {date(2026, 1, 5): 2_000, date(2026, 1, 6): 5_000, date(2026, 1, 7): 9_000, date(2026, 1, 8): 10_000}
        result = squares(compute_progress(self.daily_goal(), [activity(day, v) for day, v in values.items()], TODAY), TODAY)
        self.assertEqual([c.css for c in result.weeks[1][:5]], ["l1", "l2", "l3", "l4", "l0"])
        self.assertEqual((result.active_days, result.streak_label, result.count_label), (1, "day streak", "days hit"))
