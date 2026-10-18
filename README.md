# Goals 🎯

Yearly goals that track themselves. Sources (Strava, GitHub, PyPI, an RSS feed, Goodreads, Mastodon, or anything that can
POST to a webhook) are synced every 15 minutes by a [potatoq](https://github.com/anze3db/potatoq) worker. Each goal picks
a metric from a source and a yearly target. Goals nothing can measure get a Log button instead.

- **Today** (`/`): pace charts per goal, what was captured recently, and the goals you log by hand
- **Year** (`/year/`): one square per day per goal, with streaks
- **Report** (`/u/<username>/<year>/`): a shareable year report, public once you turn it on in Settings
- **Sources** (`/sources/`): connect services, sync now, webhook URLs
- **Archive** (`/archive/`): the old hand-filled monthly boards, read-only

## Dev set up

Install [uv](https://docs.astral.sh/uv/getting-started/installation/)

```
cp .env.example .env
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py collectstatic
uv run python manage.py runserver
uv run python manage.py potatoq worker   # syncs sources; the database is the broker
uv run ptw
```

## Sources

| Source | Setup | Metrics |
|---|---|---|
| Strava | OAuth; needs `STRAVA_CLIENT_ID`/`STRAVA_CLIENT_SECRET` | km run/ridden/swum/walked/hiked, surf sessions, ski days, strength workouts |
| GitHub | Username, optional token (needed for contributions) | releases, daily contributions |
| PyPI | Username and/or package names | releases |
| RSS / Atom | Feed URL, e.g. `https://blog.pecar.me/feed.xml` | posts |
| Goodreads | User id (the shelf RSS; the API is gone) | books read |
| Mastodon | `@you@instance` | posts, likes/boosts/replies, followers |
| Webhook | Nothing; POST `type`, `value`, `date` | anything: Apple Health steps via iOS Shortcuts, surf sessions, ... |

## Deploying

`.deploy/update.sh` pulls, syncs, migrates and restarts. The worker runs as its own service:

```
sudo cp .deploy/goals-worker.service /etc/systemd/system/
sudo systemctl enable --now goals-worker
```
