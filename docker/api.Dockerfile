# API and worker image (FastAPI engine + data worker). Settings come from .env at runtime.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends cron postgresql-client curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/venv PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
