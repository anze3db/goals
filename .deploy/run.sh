#!/bin/bash
set -e
pushd "$(dirname "$0")/.."
uv run --locked gunicorn goals.wsgi
popd
