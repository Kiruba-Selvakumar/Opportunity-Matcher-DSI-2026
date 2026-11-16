# Build the web app, then run the API and serve the built app from one container.
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
# This image is intentionally demo-only. Do not use it for production data.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MATCHER_DATA_ROOT=/app/data \
    DEMO_LOGIN=1 \
    COOKIE_SECURE=0 \
    DEMO_PASSWORD=secure-demo-2026 \
    RUN_PIPELINE=1 \
    SEED_DEMO=1 \
    SEED_OUTCOMES=1 \
    LLM_PROVIDER=none \
    EMBEDDINGS=tfidf
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY api ./api
COPY data/reference ./data/reference
RUN pip install --no-cache-dir -e .
COPY --from=web /web/dist ./web/dist
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && mkdir -p /app/data && chown -R app:app /app/data
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
  CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/ready', timeout=4).status == 200 else 1)"
ENTRYPOINT ["/entrypoint.sh"]
