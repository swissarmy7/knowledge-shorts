#!/usr/bin/env bash
set -euo pipefail
cd /var/www/html/my_shorts
mkdir -p output/agy_requests output/agy_text_requests output/logs

if command -v pm2 &> /dev/null; then
  echo "🚀 PM2 detected. Starting workers under PM2..."
  
  # Delete existing if any to avoid duplicates, then start
  pm2 delete codex-image-worker 2>/dev/null || true
  pm2 delete agy-image-worker 2>/dev/null || true
  pm2 start scripts/agy_image_worker.py --name codex-image-worker --interpreter python3.12 -- --watch-dir /var/www/html/my_shorts/output/agy_requests
  
  pm2 delete codex-text-worker 2>/dev/null || true
  pm2 delete agy-text-worker 2>/dev/null || true
  pm2 start scripts/agy_text_worker.py --name codex-text-worker --interpreter python3.12 -- --watch-dir /var/www/html/my_shorts/output/agy_text_requests

  pm2 delete agy-video-worker 2>/dev/null || true
  pm2 delete codex-video-worker 2>/dev/null || true
  
  pm2 save
  echo "✅ PM2 setup complete and saved."
else
  echo "⚠️ PM2 not found. Falling back to nohup..."
  
  # 1. Start Image Worker
  if pgrep -f "scripts/agy_image_worker.py" >/dev/null; then
    echo "codex image worker already running"
  else
    nohup env CODEX_IMAGE_WORKER_TIMEOUT="${CODEX_IMAGE_WORKER_TIMEOUT:-180}" CODEX_IMAGE_WORKER_POLL="${CODEX_IMAGE_WORKER_POLL:-0.5}" \
      python3.12 scripts/agy_image_worker.py --watch-dir /var/www/html/my_shorts/output/agy_requests \
      >> output/logs/codex_image_worker.log 2>&1 &
    echo "codex image worker started: $!"
  fi

  # 2. Start Text Worker
  if pgrep -f "scripts/agy_text_worker.py" >/dev/null; then
    echo "codex text worker already running"
  else
    nohup env CODEX_TEXT_WORKER_TIMEOUT="${CODEX_TEXT_WORKER_TIMEOUT:-300}" CODEX_TEXT_WORKER_POLL="${CODEX_TEXT_WORKER_POLL:-2.0}" \
      python3.12 scripts/agy_text_worker.py --watch-dir /var/www/html/my_shorts/output/agy_text_requests \
      >> output/logs/codex_text_worker.log 2>&1 &
    echo "codex text worker started: $!"
  fi
fi
