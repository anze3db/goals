from typing import cast

from django import forms
from django.utils import timezone

from tracker.models import Goal, Source
from tracker.providers import get_provider
from users.models import User

MANUAL = "manual"
CUSTOM = "custom"


def metric_choices(user: User) -> list[tuple[str, object]]:
    """Grouped options for "what counts toward this goal": every activity type of every source."""
    choices: list[tuple[str, object]] = [(MANUAL, "Log it by hand")]
    for source in user.sources.all():
        provider = source.provider
        options = [(f"{source.pk}:{t.slug}", f"{t.label} ({t.unit})" if t.unit else t.label) for t in provider.activity_types]
        if provider.custom_types:
            options.append((f"{source.pk}:{CUSTOM}", "Other type…"))
        choices.append((source.name, options))
    return choices


class GoalForm(forms.ModelForm):
    metric = forms.ChoiceField(label="What counts")
    custom_type = forms.SlugField(
        required=False,
        label="Activity type",
        help_text="The type your webhook sends, e.g. steps or surf",
    )
    aggregation = forms.ChoiceField(
        required=False,
        label="How to count",
        choices=[("", "Default for this metric"), *Goal.Aggregation.choices],
    )

    class Meta:
        model = Goal
        fields = ["name", "target", "unit", "year"]
        help_texts = {"unit": "Leave empty to use the metric's unit"}

    def __init__(self, *args, user: User, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        cast(forms.ChoiceField, self.fields["metric"]).choices = metric_choices(user)
        self.fields["unit"].required = False
        self.fields["year"].initial = timezone.localdate().year
        goal = self.instance
        if goal.pk:
            self.fields["aggregation"].initial = goal.aggregation
            if goal.source_id is None:
                self.fields["metric"].initial = MANUAL
            elif goal.source and goal.source.provider.activity_type(goal.activity_type):
                self.fields["metric"].initial = f"{goal.source_id}:{goal.activity_type}"
            else:
                self.fields["metric"].initial = f"{goal.source_id}:{CUSTOM}"
                self.fields["custom_type"].initial = goal.activity_type

    def clean(self):
        cleaned = super().clean()
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
        return cleaned

    def save(self, commit: bool = True) -> Goal:
        goal = super().save(commit=False)
        goal.user = self.user
        goal.source = self.cleaned_data["source"]
        goal.activity_type = self.cleaned_data["activity_type"]
        goal.aggregation = self.cleaned_data.get("aggregation") or self.cleaned_data["default_aggregation"]
        goal.unit = goal.unit or self.cleaned_data["default_unit"]
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
