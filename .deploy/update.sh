#!/bin/bash
set -e
pushd "$(dirname "$0")/.."
git pull
old_python=$(.venv/bin/python -V 2>&1 || true)
uv sync --locked
uv run python manage.py collectstatic --noinput
uv run python manage.py migrate
# A new Python version means uv rebuilt .venv under the running server, so a reload isn't enough.
if [ "$old_python" != "$(.venv/bin/python -V 2>&1)" ]; then
    sudo systemctl restart goals
else
    sudo systemctl reload goals
fi
sudo systemctl restart goals-worker
echo `date "+%Y-%m-%d %H:%M:%S.%3N"` ' Updated' >> update.log
popd
