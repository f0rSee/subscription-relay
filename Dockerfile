FROM oven/bun:1.4.0 AS frontend-builder

WORKDIR /frontend

COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile

COPY frontend/ ./
RUN bun run build

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=10000

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml .
COPY backend/ ./backend/
COPY --from=frontend-builder /frontend/dist ./frontend/dist

RUN useradd --create-home --uid 10001 relay && chown -R relay:relay /app
USER relay

EXPOSE 10000

CMD ["sh", "-c", "fastapi run --host 0.0.0.0 --port ${PORT}"]
