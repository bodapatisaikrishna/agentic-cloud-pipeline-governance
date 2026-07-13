# Airflow image with the acde package installed so DAGs can `import acde.*`.
# Airflow itself lives only in this image, never in the project venv (DEVIATIONS D-010).
FROM apache/airflow:2.10.5-python3.11

USER root
# psycopg[binary] + pandas/pyarrow wheels need no system build deps on this base.
USER airflow

# Install the acde package (runtime deps only: pydantic, psycopg, pandas, pyarrow, httpx,
# confluent-kafka, tenacity). README.md is required because pyproject sets readme=.
COPY --chown=airflow:airflow pyproject.toml README.md /opt/acde/
COPY --chown=airflow:airflow src /opt/acde/src
RUN pip install --no-cache-dir /opt/acde
