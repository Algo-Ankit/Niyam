# Niyam API image (D68). Settings and secrets come only from environment variables at run time.
#   docker build -t niyam-api .
#   docker run --rm -p 8000:8000 --env-file .env niyam-api

# Build stage: resolve the locked dependencies with the same uv minor as scripts/bootstrap.sh.
FROM python:3.12-slim AS build
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3.12 \
    UV_PROJECT_ENVIRONMENT=/app/.venv
RUN pip install --no-cache-dir --disable-pip-version-check "uv==0.13.8"
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

# Runtime stage: the virtual environment only, run as a non-root user.
FROM python:3.12-slim
RUN useradd --create-home --uid 10001 niyam
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
# The corpus snapshot date for GET /api/health (D66); the corpus itself lives in Postgres.
COPY data/manifest.json ./data/manifest.json
RUN mkdir /app/.state && chown niyam /app/.state
# FORWARDED_ALLOW_IPS: uvicorn trusts X-Forwarded-For only from these peers and takes the
# right-most untrusted address, so a client cannot spoof its IP past the host's proxy (D64, D68).
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    STATE_DIR=/app/.state \
    FORWARDED_ALLOW_IPS="10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.1"
USER niyam
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request as r; r.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '8000'), timeout=4)"
CMD ["sh", "-c", "exec uvicorn niyam.api:create_app --factory --host 0.0.0.0 --port \"$PORT\" --proxy-headers"]
