#!/bin/sh
set -e
# First start: build the match files from the sample data. Replace data/raw with real data and run
# `docker compose exec app python -m matcher.pipeline` to rebuild them.
if [ "${RUN_PIPELINE:-1}" = "1" ] && [ ! -f "$MATCHER_DATA_ROOT/derived/top5.json" ]; then
  echo "No match files yet. Running the pipeline on the sample data."
  python -m matcher.pipeline --no-llm
fi
if [ "${SEED_DEMO:-0}" = "1" ]; then
  : "${DEMO_PASSWORD:?DEMO_PASSWORD is required when SEED_DEMO=1}"
  python -m matcher.accounts seed-demo
fi
if [ "${SEED_OUTCOMES:-0}" = "1" ]; then
  python -m matcher.accounts seed-outcomes
fi
exec uvicorn api.server:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
