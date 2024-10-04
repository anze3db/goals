#!/bin/bash
set -e
pushd "$(dirname "$0")/.."
uv run gunicorn goals.wsgi
popd
