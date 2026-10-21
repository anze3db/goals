from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import cast

from django import forms
from django.db.models import Max
from django.utils import timezone

from tracker.models import Activity, Goal, Source
from tracker.progress import format_number, with_unit
from tracker.providers import get_provider
from users.models import User

MANUAL = "manual"
CUSTOM = "custom"

# What each way of counting does, shown next to it on the goal form
AGGREGATION_HELP = {
    "": "Whatever fits the metric: kilometres add up, posts are counted, followers use the latest reading "
    "(or their growth, for a weekly or monthly target).",
    Goal.Aggregation.SUM: "Each entry adds its value: a 5 km run and a 10 km run make 15 km.",
    Goal.Aggregation.COUNT: "Each entry counts as one, whatever its value: those two runs make 2.",
    Goal.Aggregation.LATEST: "The most recent reading, for reaching a number like 1,500 followers by the end of the year.",
    Goal.Aggregation.GAIN: "How much a reading went up, for targets like 10 new followers a week.",
}


@dataclass
class MetricOption:
    value: str
    label: str
    unit: str = ""
    aggregation: str = Goal.Aggregation.SUM
    summary: str = ""
    # Bar heights in percent, one per month of the year
    bars: list[int] = field(default_factory=list)
    has_data: bool = True


@dataclass
class MetricGroup:
    name: str
    options: list[MetricOption]
    # Metrics with nothing this year fold away unless one of them is picked
    show_empty: bool = False

    @property
    def filled(self) -> list[MetricOption]:
        return [option for option in self.options if option.has_data]

    @property
    def empty(self) -> list[MetricOption]:
        return [option for option in self.options if not option.has_data]


@dataclass
class _Stats:
    count: int = 0
    total: float = 0
    latest: float = 0
    last_at: datetime | None = None
    months: list[list[float]] = field(default_factory=lambda: [[] for _ in range(12)])


def _metric_stats(user: User, year: int) -> dict[tuple[int, str], _Stats]:
    stats: dict[tuple[int, str], _Stats] = defaultdict(_Stats)
    rows = Activity.objects.filter(user=user, source__isnull=False, occurred_at__year=year).order_by("occurred_at")
    for source_id, activity_type, value, occurred_at in rows.values_list("source_id", "type", "value", "occurred_at"):
        entry = stats[(source_id, activity_type)]
        entry.count += 1
        entry.total += value
        entry.latest = value
        entry.last_at = occurred_at
        entry.months[timezone.localtime(occurred_at).month - 1].append(value)
    return stats


def _describe(option: MetricOption, stats: _Stats | None) -> None:
    """This year's number for the metric as its default count would show it, and a bar per month."""
    if stats is None:
        option.summary = "Nothing this year yet"
        option.has_data = False
        return
    match option.aggregation:
        case Goal.Aggregation.COUNT:
            option.summary = f"{with_unit(format_number(stats.count), option.unit)} this year"
            per_month = [float(len(month)) for month in stats.months]
        case Goal.Aggregation.LATEST:
            option.summary = f"{with_unit(format_number(stats.latest), option.unit)} now"
            per_month = [month[-1] if month else 0.0 for month in stats.months]
        case _:
            entries = f"{format_number(stats.count)} entr{'y' if stats.count == 1 else 'ies'}"
            option.summary = f"{with_unit(format_number(stats.total), option.unit)} this year · {entries}"
            per_month = [sum(month) for month in stats.months]
    peak = max(per_month)
    option.bars = [round(value / peak * 100) if peak > 0 else 0 for value in per_month]


def metric_groups(user: User, year: int) -> list[MetricGroup]:
    """Every activity type of every source, with this year's numbers, for picking what counts toward a goal."""
    stats = _metric_stats(user, year)
    groups = [MetricGroup("By hand", [MetricOption(MANUAL, "Log it by hand", summary="A Log button on the Today page")])]
    for source in user.sources.all():
        provider = source.provider
        options = [MetricOption(f"{source.pk}:{t.slug}", t.label, t.unit, t.aggregation) for t in provider.activity_types]
        if provider.custom_types:
            # Types a webhook has already sent get their own card, so they don't have to be typed in
            known = {t.slug for t in provider.activity_types}
            seen = sorted(slug for source_id, slug in stats if source_id == source.pk and slug not in known)
            options += [MetricOption(f"{source.pk}:{slug}", slug.replace("-", " ").capitalize()) for slug in seen]
        for option in options:
            _describe(option, stats.get((source.pk, option.value.split(":", 1)[1])))
        if provider.custom_types:
            options.append(MetricOption(f"{source.pk}:{CUSTOM}", "Another type…", summary="One your webhook will send"))
        groups.append(MetricGroup(source.name, options))
    return groups


class GoalForm(forms.ModelForm):
    metric = forms.ChoiceField(label="What counts", widget=forms.RadioSelect)
    custom_type = forms.SlugField(
        required=False,
        label="Type your webhook sends",
        help_text="The type field of what it posts, e.g. swim",
    )
    aggregation = forms.ChoiceField(
        required=False,
        label="How to count",
        choices=[("", "Automatic"), *Goal.Aggregation.choices],
        widget=forms.RadioSelect,
    )

    class Meta:
        model = Goal
        fields = ["name", "group", "target", "period", "unit", "year"]
        labels = {"period": "Target applies", "unit": "Unit label"}
        help_texts = {"unit": "Only shown after the numbers, as in 1,000 km. Leave empty to use the metric's own unit."}
        widgets = {"period": forms.RadioSelect}

    def __init__(self, *args, user: User, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
        self.user = user
        goal = self.instance
        self.metric_groups = metric_groups(user, goal.year if goal.pk else timezone.localdate().year)
        choices = [(MANUAL, "Log it by hand")]
        choices += [(group.name, [(o.value, o.label) for o in group.options]) for group in self.metric_groups[1:]]
        cast(forms.ChoiceField, self.fields["metric"]).choices = choices
        cast(forms.ChoiceField, self.fields["period"]).choices = Goal.Period.choices
        group = cast(forms.ModelChoiceField, self.fields["group"])
        group.queryset = user.tracked_goal_groups.all()
        group.empty_label = "No group"
        group.help_text = "A heading on the dashboard, like Fitness. Add groups on the Arrange page."
        self.fields["unit"].required = False
        self.fields["period"].required = False
        self.fields["year"].initial = timezone.localdate().year
        if goal.pk:
            if float(goal.target).is_integer():
                self.initial["target"] = int(goal.target)
            self.fields["aggregation"].initial = goal.aggregation
            values = {option.value for group in self.metric_groups for option in group.options}
            if goal.source_id is None:
                self.fields["metric"].initial = MANUAL
            elif f"{goal.source_id}:{goal.activity_type}" in values:
                self.fields["metric"].initial = f"{goal.source_id}:{goal.activity_type}"
            else:
                self.fields["metric"].initial = f"{goal.source_id}:{CUSTOM}"
                self.fields["custom_type"].initial = goal.activity_type
        selected = self["metric"].value()
        for group in self.metric_groups:
            group.show_empty = any(option.value == selected for option in group.empty)

    @property
    def aggregation_options(self) -> list[tuple[forms.BoundField, str]]:
        return [(radio, AGGREGATION_HELP[radio.data["value"]]) for radio in self["aggregation"]]

    def clean(self):
        cleaned = super().clean()
        cleaned["period"] = cleaned.get("period") or Goal.Period.YEAR
        metric = cleaned.get("metric")
        if not metric:
            return cleaned

        if metric == MANUAL:
            cleaned["source"] = None
            cleaned["activity_type"] = ""
            cleaned["default_aggregation"] = Goal.Aggregation.SUM
            cleaned["default_unit"] = ""
            return cleaned

        source_id, slug = metric.split(":", 1)
        source = Source.objects.filter(user=self.user, pk=source_id).first()
        if source is None:
            raise forms.ValidationError("Unknown source")
        if slug == CUSTOM:
            slug = cleaned.get("custom_type", "")
            if not slug:
                self.add_error("custom_type", "Enter the activity type your webhook sends")
                return cleaned
        activity_type = source.provider.activity_type(slug)
        cleaned["source"] = source
        cleaned["activity_type"] = slug
        cleaned["default_aggregation"] = activity_type.aggregation if activity_type else Goal.Aggregation.SUM
        cleaned["default_unit"] = activity_type.unit if activity_type else ""
        # A weekly or monthly target on a reading like followers can only mean new followers
        if cleaned["default_aggregation"] == Goal.Aggregation.LATEST and cleaned["period"] != Goal.Period.YEAR:
            cleaned["default_aggregation"] = Goal.Aggregation.GAIN
        aggregation = cleaned.get("aggregation") or cleaned["default_aggregation"]
        if aggregation == Goal.Aggregation.LATEST and cleaned["period"] != Goal.Period.YEAR:
            self.add_error("period", "A latest value can only have a yearly target. Pick Growth to count new followers per week or month.")
        return cleaned

    def save(self, commit: bool = True) -> Goal:
        goal = super().save(commit=False)
        goal.user = self.user
        goal.source = self.cleaned_data["source"]
        goal.activity_type = self.cleaned_data["activity_type"]
        goal.aggregation = self.cleaned_data.get("aggregation") or self.cleaned_data["default_aggregation"]
        goal.unit = goal.unit or self.cleaned_data["default_unit"]
        if goal.pk is None or "group" in self.changed_data or "year" in self.changed_data:
            # A new goal, or one moved to another group or year, goes to the end of it
            siblings = Goal.objects.filter(user=self.user, year=goal.year, group=goal.group).exclude(pk=goal.pk)
            goal.position = (siblings.aggregate(last=Max("position"))["last"] or 0) + 1
        if commit:
            goal.save()
        return goal


class LogForm(forms.Form):
    amount = forms.FloatField(initial=1)
    note = forms.CharField(required=False, max_length=500)


def source_form(source_kind: str, data=None, source: Source | None = None) -> forms.Form | None:
    """The provider's config form, prefilled from an existing source. Secret fields stay empty."""
    provider = get_provider(source_kind)
    if provider.config_form is None:
        return None
    initial = {}
    if source:
        initial = {key: "\n".join(value) if isinstance(value, list) else value for key, value in source.config.items()}
    form = provider.config_form(data=data, initial=initial)
    if source:
        for name in provider.secret_fields:
            form.fields[name].required = False
            form.fields[name].help_text = "Leave empty to keep the current one. " + str(form.fields[name].help_text)
    return form


def apply_source_form(source: Source, form: forms.Form) -> None:
    provider = source.provider
    for name, value in form.cleaned_data.items():
        if name in provider.secret_fields:
            if value:
                source.secrets[name] = value
        else:
            source.config[name] = value
