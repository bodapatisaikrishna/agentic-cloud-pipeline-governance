#!/usr/bin/env bash
# One-shot Airflow bootstrap: create the metadata database (a separate `airflow` DB inside
# the shared Postgres, DEVIATIONS D-011), run migrations, and create the admin user.
set -euo pipefail

echo "[airflow-init] ensuring 'airflow' database exists"
python - <<'PY'
import os, psycopg2
con = psycopg2.connect(
    host=os.environ["POSTGRES_HOST"], port=int(os.environ["POSTGRES_PORT"]),
    user=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"],
    dbname=os.environ["POSTGRES_DB"],
)
con.autocommit = True
cur = con.cursor()
cur.execute("SELECT 1 FROM pg_database WHERE datname = 'airflow'")
if cur.fetchone():
    print("[airflow-init] airflow database already exists")
else:
    cur.execute("CREATE DATABASE airflow")
    print("[airflow-init] created airflow database")
PY

echo "[airflow-init] running db migrate"
airflow db migrate

echo "[airflow-init] ensuring admin user"
airflow users create \
  --username "${AIRFLOW_USER}" --password "${AIRFLOW_PASSWORD}" \
  --firstname ACDE --lastname Admin --role Admin --email admin@example.com \
  || echo "[airflow-init] admin user already present"

echo "[airflow-init] done"
