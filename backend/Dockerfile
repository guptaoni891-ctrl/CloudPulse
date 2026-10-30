# syntax=docker/dockerfile:1
FROM python:3.12-slim AS runtime
WORKDIR /app
COPY backend/pyproject.toml ./
COPY constraints.txt /tmp/constraints.txt
COPY backend/app ./app
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -c /tmp/constraints.txt .
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
RUN chmod -R a+rX /app && useradd --uid 10001 --create-home cloudpulse
USER cloudpulse
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

# Test-only target; production images finish at the runtime stage.
FROM runtime AS test
USER root
COPY agent /agent
COPY tests /tests
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -c /tmp/constraints.txt /agent pytest httpx
COPY scripts /scripts
RUN chmod -R a+rX /tests /agent /scripts
USER cloudpulse
CMD ["pytest", "-q", "-o", "cache_dir=/tmp/pytest-cache", "/tests"]
