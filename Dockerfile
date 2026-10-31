FROM node:22-alpine AS frontend
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.15-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       curl ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml /tmp/chatbi/pyproject.toml
RUN mkdir -p /tmp/chatbi && pip install --upgrade pip
RUN pip install torch --index-url https://download.pytorch.org/whl/cu128
RUN pip install /tmp/chatbi
RUN groupadd --gid 10001 chatbi \
    && useradd --uid 10001 --gid chatbi --create-home --shell /usr/sbin/nologin chatbi

WORKDIR /app
COPY --chown=chatbi:chatbi backend ./backend
COPY --chown=chatbi:chatbi data/runtime ./data/runtime
COPY --from=frontend --chown=chatbi:chatbi /ui/dist ./frontend/dist
COPY docker-entrypoint.sh /usr/local/bin/chatbi-entrypoint
RUN chmod +x /usr/local/bin/chatbi-entrypoint \
    && mkdir -p /tmp/chatbi \
    && chown -R chatbi:chatbi /app /tmp/chatbi

ENV HOME=/tmp/chatbi
USER chatbi

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=8s --start-period=90s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

ENTRYPOINT ["chatbi-entrypoint"]
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
