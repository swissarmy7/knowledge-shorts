#!/usr/bin/env bash
set -euo pipefail
cd /var/www/html/my_shorts
mkdir -p output/agy_requests output/logs
if pgrep -f "scripts/agy_image_worker.py --watch-dir /var/www/html/my_shorts/output/agy_requests" >/dev/null; then
  echo "codex image worker already running"
  exit 0
fi
nohup env CODEX_IMAGE_WORKER_TIMEOUT="${CODEX_IMAGE_WORKER_TIMEOUT:-180}" CODEX_IMAGE_WORKER_POLL="${CODEX_IMAGE_WORKER_POLL:-0.5}" \
  python3 scripts/agy_image_worker.py --watch-dir /var/www/html/my_shorts/output/agy_requests \
  >> output/logs/codex_image_worker.log 2>&1 &
echo "codex image worker started: $!"
