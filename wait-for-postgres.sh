#!/bin/sh
# wait-for-postgres.sh

set -e

cmd="$@"

wait_for_postgres() {
  python - <<'PY'
import os
import time
import psycopg2

db_url = os.environ.get("DATABASE_URL", "").strip().strip('"').strip("'")

if not db_url:
    print("DATABASE_URL is required")
    raise SystemExit(1)

for _ in range(90):
    try:
        conn = psycopg2.connect(db_url, connect_timeout=3)
        conn.close()
        print("Postgres is up")
        raise SystemExit(0)
    except Exception:
        print("Postgres is unavailable - sleeping")
        time.sleep(1)

print("Postgres did not become available in time")
raise SystemExit(1)
PY
}

wait_for_postgres

>&2 echo "Postgres is up - executing command"
exec $cmd
