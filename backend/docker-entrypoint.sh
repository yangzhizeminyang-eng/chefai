#!/bin/sh
# This file must use LF line endings so Linux can resolve the shebang.
set -eu

mkdir -p /app/uploads /app/assets/recipe_covers
chown app:app /app/uploads /app/assets/recipe_covers

exec gosu app sh -c 'alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port "${APP_PORT:-8000}"'
