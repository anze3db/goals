#!/bin/bash
set -e
pushd "$(dirname "$0")/.."
git pull
uv run --frozen python manage.py collectstatic --noinput
uv run --frozen python manage.py migrate
sudo kill -hup `cat gunicorn.pid`
echo `date "+%Y-%m-%d %H:%M:%S.%3N"` ' Updated' >> update.log
popd
