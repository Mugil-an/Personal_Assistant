#!/bin/sh
# wait-for-postgres.sh

set -e

host="$1"
shift
cmd="$@"

# If DATABASE_URL exists (Render-style), use it directly.
if [ -n "$DATABASE_URL" ]; then
  until psql "$DATABASE_URL" -c '\q' >/dev/null 2>&1; do
    >&2 echo "Postgres via DATABASE_URL is unavailable - sleeping"
    sleep 1
  done
else
  until PGPASSWORD=$POSTGRES_PASSWORD psql -h "$host" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\q' >/dev/null 2>&1; do
    >&2 echo "Postgres is unavailable - sleeping"
    sleep 1
  done
fi

>&2 echo "Postgres is up - executing command"
exec $cmd
