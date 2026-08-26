# Airflow image with the acde package installed so DAGs can `import acde.*`.
# Airflow itself lives only in this image, never in the project venv (DEVIATIONS D-010).

# Export the project's frozen, uv.lock-pinned dependency versions. A plain `pip install
# /opt/acde` in the final stage re-resolves acde's deps fresh against whatever's newest on
# PyPI at build time -- non-reproducible, and it breaks the moment an unrelated upstream
# release (e.g. a new uvicorn) introduces a conflict, exactly as happened in CI. Exporting
# from uv.lock first pins this image to the same versions as everywhere else in the project.
FROM python:3.11-slim AS lock-export
RUN pip install --no-cache-dir uv
WORKDIR /opt/acde
COPY pyproject.toml uv.lock README.md ./
RUN uv export --frozen --format requirements-txt --no-emit-project > /tmp/requirements.lock.txt

FROM apache/airflow:2.10.5-python3.11

USER root
# psycopg[binary] + pandas/pyarrow wheels need no system build deps on this base.
USER airflow

# Install acde's full core dependency set (pydantic, psycopg, pandas, pyarrow, httpx,
# confluent-kafka, tenacity, fastapi/uvicorn, the LLM SDKs) at the pinned versions above,
# then the acde package itself with --no-deps since its deps are already satisfied.
COPY --from=lock-export /tmp/requirements.lock.txt /tmp/requirements.lock.txt
RUN pip install --no-cache-dir -r /tmp/requirements.lock.txt
COPY --chown=airflow:airflow pyproject.toml README.md /opt/acde/
COPY --chown=airflow:airflow src /opt/acde/src
RUN pip install --no-cache-dir --no-deps /opt/acde
