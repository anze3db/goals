#!/bin/bash
set -e
pushd "$(dirname "$0")/.."
git pull
uv sync --locked
uv run python manage.py collectstatic --noinput
uv run python manage.py migrate
ps axf | grep 'gunicorn: master \[goals\]' | awk '{print "sudo kill -hup " $1}' | sh
echo `date "+%Y-%m-%d %H:%M:%S.%3N"` ' Updated' >> update.log
popd
