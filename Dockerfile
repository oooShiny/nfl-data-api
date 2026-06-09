FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY pipeline/ ./pipeline/
COPY api/ ./api/

# Map Fly.io persistent volume (/data) to the path pipeline/config.py expects
RUN ln -s /data /app/data

EXPOSE 8000

CMD [".venv/bin/uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
