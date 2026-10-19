import json
import secrets
from dataclasses import dataclass
from datetime import date, datetime
from typing import cast

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from tracker.forms import GoalForm, LogForm, apply_source_form, source_form
from tracker.models import Activity, Goal, Source, WebhookDelivery
from tracker.progress import (
    MONTH_NAMES,
    day_of_year,
    days_in_year,
    format_number,
    headline,
    month_bars,
    progress_for_goals,
    squares,
    year_fraction,
)
from tracker.providers import PROVIDERS, FetchedActivity, SyncError, get_provider
from tracker.providers.base import midday
from tracker.providers.strava import authorize_url, request_token, tokens_to_secrets
from tracker.sync import make_client, store_activities
from tracker.tasks import sync_source_task
from users.http import AuthenticatedHttpRequest
from users.models import User

WEBHOOK_BATCH_LIMIT = 1000


def _year(request: HttpRequest) -> int:
    try:
        return int(request.GET.get("year", ""))
    except ValueError:
        return timezone.localdate().year


def _year_links(user: User, year: int) -> list[int]:
    years = set(Goal.objects.filter(user=user).values_list("year", flat=True))
    years.update({year, timezone.localdate().year})
    return sorted(years)


@dataclass
class FeedItem:
    activity: Activity
    monogram: str
    goal_name: str
    delta: str


def _feed(user: User, goals: list[Goal], limit: int = 8) -> list[FeedItem]:
    goals_by_metric: dict[tuple[int | None, str], Goal] = {(g.source_id, g.activity_type): g for g in goals if g.source_id}
    items = []
    for activity in Activity.objects.filter(user=user).select_related("source", "goal")[:limit]:
        goal = activity.goal or goals_by_metric.get((activity.source_id, activity.type))
        latest = goal is not None and goal.aggregation == Goal.Aggregation.LATEST
        counted = goal is not None and goal.aggregation == Goal.Aggregation.COUNT
        delta = format_number(activity.value) if latest else f"+{format_number(1 if counted else activity.value)}"
        items.append(
            FeedItem(
                activity=activity,
                monogram=activity.source.provider.label[:2] if activity.source else "Me",
                goal_name=goal.name if goal else "",
                delta=delta,
            )
        )
    return items


def index(request: HttpRequest) -> HttpResponse:
    if not request.user.is_authenticated:
        return render(request, "tracker/landing.html")
    return dashboard(cast(AuthenticatedHttpRequest, request))


@login_required
def dashboard(request: AuthenticatedHttpRequest) -> HttpResponse:
    user = request.user
    year = _year(request)
    today = timezone.localdate()
    goals = list(Goal.objects.filter(user=user, year=year).select_related("source"))
    progress = progress_for_goals(goals, today)
    manual = [p for p in progress if p.goal.is_manual]
    sources = list(user.sources.all())
    synced = [s.last_synced_at for s in sources if s.last_synced_at]

    if year == today.year:
        day_label = f"{today:%A %-d %B} · day {day_of_year(today)} of {days_in_year(year)}"
    elif year < today.year:
        day_label = f"{year} · final"
    else:
        day_label = f"{year} · not started"

    return render(
        request,
        "tracker/dashboard.html",
        {
            "nav": "today",
            "year": year,
            "years": _year_links(user, year),
            "day_label": day_label,
            "year_percent": f"{year_fraction(year, today) * 100:.1f}",
            "headline": headline(progress, len(manual)),
            "progress": progress,
            "manual": manual,
            "feed": _feed(user, goals),
            "last_synced": max(synced) if synced else None,
            "failing_sources": [s for s in sources if s.last_error],
            "has_sources": bool(sources),
            "month_initials": [name[0] for name in MONTH_NAMES],
        },
    )


@login_required
def year_view(request: AuthenticatedHttpRequest) -> HttpResponse:
    year = _year(request)
    goals = list(Goal.objects.filter(user=request.user, year=year).select_related("source"))
    today = timezone.localdate()
    return render(
        request,
        "tracker/year.html",
        {
            "nav": "year",
            "year": year,
            "years": _year_links(request.user, year),
            "rows": [squares(p, today) for p in progress_for_goals(goals, today)],
        },
    )


@dataclass
class Highlight:
    title: str
    meta: str


def _highlights(progress, featured, bars) -> list[Highlight]:
    highlights = []
    if featured and featured.goal.aggregation == Goal.Aggregation.SUM:
        best = next((b for b in bars if b.best), None)
        if best:
            highlights.append(Highlight(f"Best month: {best.name}, {best.label} {featured.goal.unit}".strip(), featured.goal.name))
        biggest = featured.goal.activities().order_by("-value").first()
        if biggest:
            highlights.append(
                Highlight(
                    f"Biggest single: {format_number(biggest.value)} {featured.goal.unit}".strip(),
                    f"{biggest.title or featured.goal.name} · {timezone.localtime(biggest.occurred_at):%-d %B}",
                )
            )
    streaks = [(squares(p).best_streak, p.goal.name) for p in progress]
    if streaks and max(streaks)[0] > 1:
        days, name = max(streaks)
        highlights.append(Highlight(f"Longest streak: {days} days", name))
    for p in progress:
        if p.completed_on:
            highlights.append(Highlight(f"{p.goal.name}: done", f"Reached on {p.completed_on:%-d %B}"))
    return highlights


def report(request: HttpRequest, username: str, year: int) -> HttpResponse:
    owner = get_object_or_404(User, username=username)
    if owner != request.user and not owner.public_report:
        raise Http404
    goals = list(Goal.objects.filter(user=owner, year=year).select_related("source"))
    progress = progress_for_goals(goals)
    featured = next((p for p in progress if p.goal.aggregation == Goal.Aggregation.SUM and p.daily), None)
    bars = month_bars(featured) if featured else []
    sources = sorted({g.source.provider.label for g in goals if g.source})
    return render(
        request,
        "tracker/report.html",
        {
            "owner": owner,
            "year": year,
            "progress": progress,
            "featured": featured,
            "bars": bars,
            "highlights": _highlights(progress, featured, bars),
            "sources": sources,
            "is_owner": owner == request.user,
            "live": year == timezone.localdate().year,
        },
    )


@login_required
def my_report(request: AuthenticatedHttpRequest) -> HttpResponse:
    return redirect("report", username=request.user.username, year=_year(request))


@login_required
def goal_new(request: AuthenticatedHttpRequest) -> HttpResponse:
    form = GoalForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        goal = form.save()
        messages.success(request, f"Added {goal.name}")
        return redirect(f"{reverse('index')}?year={goal.year}")
    return render(request, "tracker/goal_form.html", {"form": form, "nav": "today"})


@login_required
def goal_edit(request: AuthenticatedHttpRequest, pk: int) -> HttpResponse:
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    form = GoalForm(request.POST or None, instance=goal, user=request.user)
    if request.method == "POST" and form.is_valid():
        goal = form.save()
        messages.success(request, f"Saved {goal.name}")
        return redirect(f"{reverse('index')}?year={goal.year}")
    return render(request, "tracker/goal_form.html", {"form": form, "goal": goal, "nav": "today"})


@login_required
@require_POST
def goal_delete(request: AuthenticatedHttpRequest, pk: int) -> HttpResponse:
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    goal.delete()
    messages.success(request, f"Deleted {goal.name}")
    return redirect(f"{reverse('index')}?year={goal.year}")


@login_required
@require_POST
def goal_log(request: AuthenticatedHttpRequest, pk: int) -> HttpResponse:
    goal = get_object_or_404(Goal, pk=pk, user=request.user, source__isnull=True)
    form = LogForm(request.POST)
    if form.is_valid():
        now = timezone.now()
        occurred_at = now if goal.year == now.year else midday(date(goal.year, 12, 31))
        Activity.objects.create(
            user=request.user,
            goal=goal,
            type="manual",
            value=form.cleaned_data["amount"],
            title=form.cleaned_data["note"],
            occurred_at=occurred_at,
        )
        messages.success(request, f"Logged {format_number(form.cleaned_data['amount'])} on {goal.name}")
    else:
        messages.error(request, "Enter a number to log")
    return redirect(f"{reverse('index')}?year={goal.year}")


@login_required
def sources(request: AuthenticatedHttpRequest) -> HttpResponse:
    user_sources = list(request.user.sources.all())
    return render(
        request,
        "tracker/sources.html",
        {
            "nav": "sources",
            "sources": user_sources,
            "providers": PROVIDERS.values(),
            "recent": Activity.objects.filter(user=request.user, source__isnull=False).select_related("source")[:8],
            "strava_configured": bool(settings.STRAVA_CLIENT_ID),
        },
    )


@login_required
def source_new(request: AuthenticatedHttpRequest, kind: str) -> HttpResponse:
    if kind not in PROVIDERS:
        raise Http404
    provider = get_provider(kind)
    if provider.connect_url_name:
        return redirect(provider.connect_url_name)
    form = source_form(kind, request.POST or None)
    if request.method == "POST" and (form is None or form.is_valid()):
        source = Source(user=request.user, kind=kind)
        if form is not None:
            apply_source_form(source, form)
        source.name = provider.default_name(source.config)
        source.save()
        if provider.pulls:
            sync_source_task.delay(source.pk)
            messages.success(request, f"Connected {source.name}. Importing this year's history now.")
        else:
            messages.success(request, f"Created {source.name}")
        return redirect("sources")
    return render(request, "tracker/source_form.html", {"form": form, "provider": provider, "nav": "sources"})


@login_required
def source_edit(request: AuthenticatedHttpRequest, pk: int) -> HttpResponse:
    source = get_object_or_404(Source, pk=pk, user=request.user)
    form = source_form(source.kind, request.POST or None, source=source)
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if form is None or form.is_valid():
            if form is not None:
                apply_source_form(source, form)
            source.name = name or source.name
            source.enabled = request.POST.get("enabled") == "on"
            source.save()
            messages.success(request, f"Saved {source.name}")
            return redirect("sources")
    return render(
        request,
        "tracker/source_form.html",
        {
            "form": form,
            "provider": source.provider,
            "source": source,
            "webhook_url": request.build_absolute_uri(reverse("webhook", args=[source.webhook_token])),
            "deliveries": source.deliveries.all()[:20],
            "nav": "sources",
        },
    )


@login_required
@require_POST
def source_delete(request: AuthenticatedHttpRequest, pk: int) -> HttpResponse:
    source = get_object_or_404(Source, pk=pk, user=request.user)
    source.delete()
    messages.success(request, f"Removed {source.name} and its activities")
    return redirect("sources")


@login_required
@require_POST
def source_sync(request: AuthenticatedHttpRequest, pk: int) -> HttpResponse:
    source = get_object_or_404(Source, pk=pk, user=request.user)
    sync_source_task.delay(source.pk)
    messages.success(request, f"Syncing {source.name}")
    return redirect("sources")


@login_required
def strava_connect(request: AuthenticatedHttpRequest) -> HttpResponse:
    if not settings.STRAVA_CLIENT_ID:
        messages.error(request, "Set STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET to connect Strava.")
        return redirect("sources")
    state = secrets.token_urlsafe(16)
    request.session["strava_state"] = state
    return redirect(authorize_url(request.build_absolute_uri(reverse("strava_callback")), state))


@login_required
def strava_callback(request: AuthenticatedHttpRequest) -> HttpResponse:
    expected_state = request.session.pop("strava_state", None)
    if not expected_state or request.GET.get("state") != expected_state:
        messages.error(request, "Strava connection expired, try again.")
        return redirect("sources")
    if "error" in request.GET or "code" not in request.GET:
        messages.error(request, "Strava access wasn't granted.")
        return redirect("sources")

    try:
        with make_client() as client:
            tokens = request_token(client, code=request.GET["code"], grant_type="authorization_code")
    except SyncError as e:
        messages.error(request, str(e))
        return redirect("sources")

    athlete = tokens.get("athlete", {})
    source = Source.objects.filter(user=request.user, kind="strava", config__athlete_id=athlete.get("id")).first()
    if source is None:
        source = Source(user=request.user, kind="strava")
    source.config = {"athlete_id": athlete.get("id"), "athlete_name": athlete.get("firstname", "")}
    source.secrets = tokens_to_secrets(tokens)
    source.name = source.name or source.provider.default_name(source.config)
    source.save()
    sync_source_task.delay(source.pk)
    messages.success(request, f"Connected {source.name}. Importing this year's activities now.")
    return redirect("sources")


class WebhookError(ValueError):
    pass


def _webhook_activity(item: object) -> FetchedActivity:
    if not isinstance(item, dict):
        raise WebhookError("Each item must be an object")
    activity_type = str(item.get("type") or "event").strip().lower()[:64]
    try:
        value = float(item.get("value", 1))
    except TypeError, ValueError:
        raise WebhookError("value must be a number") from None

    day = item.get("date")
    try:
        if day:
            occurred_at = midday(date.fromisoformat(str(day)))
        elif item.get("occurred_at"):
            occurred_at = datetime.fromisoformat(str(item["occurred_at"]))
            if timezone.is_naive(occurred_at):
                occurred_at = timezone.make_aware(occurred_at)
        else:
            occurred_at = timezone.now()
    except ValueError:
        raise WebhookError("date must be YYYY-MM-DD and occurred_at ISO 8601") from None

    # A value per type per day (like steps) replaces the earlier report for that day
    external_id = str(item.get("id") or (f"{activity_type}:{day}" if day else ""))[:255]
    return FetchedActivity(
        type=activity_type,
        external_id=external_id,
        occurred_at=occurred_at,
        value=value,
        title=str(item.get("title", ""))[:500],
    )


def _handle_webhook(request: HttpRequest, source: Source, body: bytes) -> tuple[int, dict]:
    if not source.enabled:
        return 403, {"error": "This webhook is disabled"}
    if request.content_type == "application/json":
        try:
            payload = json.loads(body)
        except ValueError:
            return 400, {"error": "Invalid JSON"}
    else:
        payload = request.POST.dict()

    items = payload if isinstance(payload, list) else [payload]
    if len(items) > WEBHOOK_BATCH_LIMIT:
        return 400, {"error": f"At most {WEBHOOK_BATCH_LIMIT} items per request"}
    try:
        fetched = [_webhook_activity(item) for item in items]
    except WebhookError as e:
        return 400, {"error": str(e)}

    created = store_activities(source, fetched)
    source.last_synced_at = timezone.now()
    source.save(update_fields=["last_synced_at"])
    return 200, {"ok": True, "created": created, "received": len(fetched)}


@csrf_exempt
@require_POST
def webhook(request: HttpRequest, token: str) -> JsonResponse:
    source = get_object_or_404(Source, webhook_token=token, kind="webhook")
    # Read before request.POST: once a multipart body is parsed, the raw bytes are gone
    body = request.body
    status, response = _handle_webhook(request, source, body)
    WebhookDelivery.record(source, request, body, status, response)
    return JsonResponse(response, status=status)
