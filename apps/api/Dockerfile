# Field Shift Togo API — build from the REPOSITORY ROOT (the image needs data/, packs/, pipeline/):
#   docker build -f apps/api/Dockerfile -t fieldshift-api .
# NOTE: written without Docker available on the dev machine -> not tested yet (see README).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PACKS_DIR=/srv/packs \
    DATA_DIR=/srv/data \
    PORT=8000

WORKDIR /srv

# Dependencies first (better layer cache)
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/api/app apps/api/app
RUN pip install -e ./apps/api

COPY apps/api/alembic.ini apps/api/alembic.ini
COPY apps/api/alembic apps/api/alembic
COPY pipeline pipeline
COPY data data
COPY packs packs

RUN useradd --create-home --uid 10001 app && chown -R app /srv
USER app
WORKDIR /srv/apps/api
EXPOSE 8000

# Migrations + idempotent seed at start, then the API. Packs are read from /srv/packs (never
# generated at runtime; rebuild them with `python -m pipeline.run_all` and redeploy).
CMD ["sh", "-c", "alembic upgrade head && python -m app.cli seed && uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers"]
