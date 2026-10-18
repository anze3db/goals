import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.utils import timezone

from tracker.models import Activity, Goal

# Within this share of the target counts as "on pace"
PACE_TOLERANCE = 0.03

CHART_WIDTH = 320
CHART_HEIGHT = 110
CHART_PADDING = 6

MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def format_number(value: float) -> str:
    if abs(value) >= 100 or float(value).is_integer():
        return f"{round(value):,}"
    return f"{value:,.1f}"


def days_in_year(year: int) -> int:
    return (date(year + 1, 1, 1) - date(year, 1, 1)).days


def day_of_year(day: date) -> int:
    return day.timetuple().tm_yday


def year_fraction(year: int, today: date) -> float:
    """How much of the year has passed, counting today as done."""
    if today.year < year:
        return 0.0
    if today.year > year:
        return 1.0
    return day_of_year(today) / days_in_year(year)


def local_day(activity: Activity) -> date:
    return timezone.localtime(activity.occurred_at).date()


def daily_values(goal: Goal, activities: Sequence[Activity]) -> dict[date, float]:
    """One number per day: the day's sum, count, or (for "latest" goals) the last reading."""
    values: dict[date, float] = defaultdict(float)
    for activity in sorted(activities, key=lambda a: a.occurred_at):
        day = local_day(activity)
        match goal.aggregation:
            case Goal.Aggregation.COUNT:
                values[day] += 1
            case Goal.Aggregation.LATEST:
                values[day] = activity.value
            case _:
                values[day] += activity.value
    return dict(sorted(values.items()))


def cumulative(goal: Goal, daily: dict[date, float]) -> list[tuple[date, float]]:
    """Progress at the end of each day that had activity."""
    if goal.aggregation == Goal.Aggregation.LATEST:
        return list(daily.items())
    total = 0.0
    points = []
    for day, value in daily.items():
        total += value
        points.append((day, total))
    return points


@dataclass
class Chart:
    actual: str
    area: str
    pace: str
    projection: str
    today_x: str
    label: str


@dataclass
class GoalProgress:
    goal: Goal
    current: float
    baseline: float
    expected: float
    projected: float
    fraction: float
    status: str
    activity_count: int
    daily: dict[date, float]
    points: list[tuple[date, float]]
    completed_on: date | None
    chart: Chart | None = field(default=None)

    @property
    def done(self) -> bool:
        return self.status == "done"

    @property
    def delta(self) -> float:
        return self.current - self.expected

    @property
    def percent(self) -> float:
        span = self.goal.target - self.baseline
        if span <= 0:
            return 100.0
        return max(0.0, min(100.0, (self.current - self.baseline) / span * 100))

    @property
    def chip(self) -> str:
        unit = f" {self.goal.unit}" if self.goal.unit else ""
        match self.status:
            case "done":
                extra = self.current - self.goal.target
                return f"Done · +{format_number(extra)}" if extra > 0 else "Done"
            case "ahead":
                return f"+{format_number(self.delta)}{unit} ahead"
            case "behind":
                return f"{format_number(-self.delta)}{unit} behind"
            case _:
                return "On pace"

    @property
    def current_label(self) -> str:
        return format_number(self.current)

    @property
    def target_label(self) -> str:
        return format_number(self.goal.target)

    @property
    def projected_label(self) -> str:
        return format_number(self.projected)


def compute_progress(goal: Goal, activities: Sequence[Activity], today: date | None = None) -> GoalProgress:
    today = today or timezone.localdate()
    fraction = year_fraction(goal.year, today)
    daily = daily_values(goal, activities)
    points = cumulative(goal, daily)

    if goal.aggregation == Goal.Aggregation.LATEST:
        baseline = points[0][1] if points else 0.0
        current = points[-1][1] if points else 0.0
    else:
        baseline = 0.0
        current = points[-1][1] if points else 0.0

    expected = baseline + (goal.target - baseline) * fraction
    projected = baseline + (current - baseline) / fraction if fraction else current
    completed_on = next((day for day, value in points if value >= goal.target), None)

    tolerance = max(abs(goal.target - baseline) * PACE_TOLERANCE, 1e-9)
    if completed_on:
        status = "done"
    elif current - expected > tolerance:
        status = "ahead"
    elif expected - current > tolerance:
        status = "behind"
    else:
        status = "pace"

    progress = GoalProgress(
        goal=goal,
        current=current,
        baseline=baseline,
        expected=expected,
        projected=projected,
        fraction=fraction,
        status=status,
        activity_count=len(activities),
        daily=daily,
        points=points,
        completed_on=completed_on,
    )
    progress.chart = build_chart(progress)
    return progress


def build_chart(progress: GoalProgress) -> Chart:
    """SVG paths for the burn-up chart: actual progress, the even-pace line and the year-end projection."""
    goal = progress.goal
    total_days = days_in_year(goal.year)
    low = progress.baseline
    # Keep an early-year projection from flattening everything else
    high = max(goal.target, progress.current, min(progress.projected, goal.target * 1.5))
    high = low + (high - low) * 1.08 if high > low else low + 1

    def x(fraction: float) -> str:
        return f"{CHART_PADDING + fraction * (CHART_WIDTH - 2 * CHART_PADDING):.1f}"

    def y(value: float) -> str:
        share = (value - low) / (high - low)
        clamped = max(0.0, min(1.0, share))
        return f"{CHART_HEIGHT - CHART_PADDING - clamped * (CHART_HEIGHT - 2 * CHART_PADDING):.1f}"

    segments = [f"M{x(0)} {y(low)}"]
    for day, value in progress.points:
        if day.year != goal.year:
            continue
        segments.append(f"L{x(day_of_year(day) / total_days)} {y(value)}")
    segments.append(f"L{x(progress.fraction)} {y(progress.current)}")
    actual = " ".join(segments)

    projection = ""
    if 0 < progress.fraction < 1 and not progress.done:
        projection = f"M{x(progress.fraction)} {y(progress.current)} L{x(1)} {y(progress.projected)}"

    return Chart(
        actual=actual,
        area=f"{actual} L{x(progress.fraction)} {y(low)} L{x(0)} {y(low)} Z",
        pace=f"M{x(0)} {y(low)} L{x(1)} {y(goal.target)}",
        projection=projection,
        today_x=x(progress.fraction),
        label=(
            f"{goal.name}: {progress.current_label} of {progress.target_label} {goal.unit}, "
            f"projected {progress.projected_label} by the end of the year"
        ),
    )


def progress_for_goals(goals: Sequence[Goal], today: date | None = None) -> list[GoalProgress]:
    return [compute_progress(goal, list(goal.activities()), today) for goal in goals]


def headline(progress: Sequence[GoalProgress], manual_count: int) -> str:
    words = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")

    def say(n: int) -> str:
        return words[n] if n < len(words) else str(n)

    counts = {status: sum(1 for p in progress if p.status == status) for status in ("done", "ahead", "pace", "behind")}
    parts = []
    if counts["done"]:
        parts.append(f"{say(counts['done'])} done")
    if counts["ahead"]:
        parts.append(f"ahead on {say(counts['ahead'])}")
    if counts["pace"]:
        parts.append(f"on pace on {say(counts['pace'])}")
    if counts["behind"]:
        parts.append(f"behind on {say(counts['behind'])}")
    if not parts:
        return "No goals yet. Connect a source and add one."

    sentence = ", ".join(parts)
    sentence = sentence[0].upper() + sentence[1:] + "."
    if manual_count:
        return f"{sentence} {say(manual_count).capitalize()} tracked by hand."
    return f"{sentence} Nothing to log today."


@dataclass
class Squares:
    progress: GoalProgress
    weeks: list[list[str]]
    month_slots: list[str]
    streak: int
    best_streak: int
    active_days: int


def _streaks(active: set[date], start: date, today: date) -> tuple[int, int]:
    best = run = 0
    day = start
    while day <= today:
        run = run + 1 if day in active else 0
        best = max(best, run)
        day += timedelta(days=1)

    # A day without activity yet doesn't break the streak until it's over
    day = today if today in active else today - timedelta(days=1)
    current = 0
    while day in active:
        current += 1
        day -= timedelta(days=1)
    return current, best


def _levels(values: Sequence[float]) -> list[float]:
    """Quartile thresholds over the non-zero days, so intensity is relative to the goal itself."""
    ordered = sorted(v for v in values if v > 0)
    if not ordered:
        return [math.inf, math.inf, math.inf]
    if ordered[0] == ordered[-1]:
        # Every active day looks the same (one book, one post): show them all at full strength
        return [0.0, 0.0, 0.0]
    return [ordered[int((len(ordered) - 1) * q)] for q in (0.25, 0.5, 0.75)]


def squares(progress: GoalProgress, today: date | None = None) -> Squares:
    """A GitHub-style grid: one column per week (Monday first), one cell per day."""
    today = today or timezone.localdate()
    goal = progress.goal
    start = date(goal.year, 1, 1)
    end = date(goal.year, 12, 31)
    last = min(today, end)

    if goal.aggregation == Goal.Aggregation.LATEST:
        # For readings like followers, a good day is one where the number went up
        per_day: dict[date, float] = {}
        previous = progress.baseline
        for day, value in progress.daily.items():
            per_day[day] = max(0.0, value - previous)
            previous = value
    else:
        per_day = progress.daily

    thresholds = _levels(list(per_day.values()))
    offset = start.weekday()
    week_count = math.ceil((offset + days_in_year(goal.year)) / 7)

    weeks = []
    for week in range(week_count):
        cells = []
        for weekday in range(7):
            day = start + timedelta(days=week * 7 + weekday - offset)
            if day.year != goal.year:
                cells.append("out")
            elif day > last:
                cells.append("future")
            else:
                value = per_day.get(day, 0)
                level = 0 if value <= 0 else 1 + sum(value > t for t in thresholds)
                cells.append(f"l{level} today" if day == today else f"l{level}")
        weeks.append(cells)

    month_slots = [""] * week_count
    for month in range(12):
        first = date(goal.year, month + 1, 1)
        month_slots[(day_of_year(first) - 1 + offset) // 7] = MONTH_NAMES[month]

    active = {day for day, value in per_day.items() if value > 0}
    streak, best = _streaks(active, start, last)
    return Squares(
        progress=progress,
        weeks=weeks,
        month_slots=month_slots,
        streak=streak,
        best_streak=best,
        active_days=len(active),
    )


@dataclass
class MonthBar:
    name: str
    value: float
    label: str
    height: int
    best: bool
    future: bool


def month_bars(progress: GoalProgress, today: date | None = None, max_height: int = 220) -> list[MonthBar]:
    today = today or timezone.localdate()
    totals = [0.0] * 12
    for day, value in progress.daily.items():
        totals[day.month - 1] += value
    peak = max(totals) or 1
    best = totals.index(max(totals)) if any(totals) else -1
    bars = []
    for index, total in enumerate(totals):
        future = date(progress.goal.year, index + 1, 1) > today
        bars.append(
            MonthBar(
                name=MONTH_NAMES[index],
                value=total,
                label=format_number(total) if total else "",
                height=round(total / peak * max_height),
                best=index == best,
                future=future,
            )
        )
    return bars
