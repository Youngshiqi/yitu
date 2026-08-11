FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PATH=/app/.venv/bin:$PATH

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src

RUN addgroup --system yitu && \
    adduser --system --ingroup yitu yitu && \
    mkdir -p /app/var/knowledge && \
    chown -R yitu:yitu /app

USER yitu

CMD [".venv/bin/uvicorn", "yitu.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
