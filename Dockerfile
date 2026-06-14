FROM node:22-slim AS frontend

WORKDIR /app

COPY package.json package-lock.json tsconfig.json tsconfig.app.json vite.config.ts ./
COPY frontend ./frontend

RUN npm ci && npm run frontend:build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY pyproject.toml README.md ./
COPY algo_trading ./algo_trading
COPY tests ./tests
COPY --from=frontend /app/algo_trading/web/dist ./algo_trading/web/dist

RUN mkdir -p /app/runs && chown -R app:app /app

USER app

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/runs', timeout=2)"

CMD ["python", "-m", "algo_trading.ui", "--host", "0.0.0.0", "--port", "8765", "--output-root", "/app/runs"]
