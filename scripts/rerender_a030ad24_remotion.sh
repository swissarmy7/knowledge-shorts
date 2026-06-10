#!/usr/bin/env bash
set -euo pipefail
cd /var/www/html/my_shorts
JOB_ID="a030ad24"
TMP_JOB="temp/1991f174"
OUT="output/shorts_${JOB_ID}.mp4"
REMOTION_OUT="output/shorts_${JOB_ID}.remotion.mp4"
BACKUP="output/shorts_${JOB_ID}.static-fallback.backup.mp4"
BROWSER="video-engine/node_modules/.remotion/chrome-for-testing/linux-arm64/chrome-headless-shell-linux-arm64/chrome-headless-shell"

if [ ! -d "$TMP_JOB/images" ] || [ ! -d "$TMP_JOB/audio" ]; then
  echo "ERROR: source assets missing: $TMP_JOB" >&2
  exit 1
fi
if [ ! -x "$BROWSER" ]; then
  echo "ERROR: Remotion browser missing: $BROWSER" >&2
  exit 1
fi

mkdir -p video-engine/public/images video-engine/public/audio
cp "$TMP_JOB"/images/scene_*.png video-engine/public/images/
cp "$TMP_JOB"/audio/narration_*.mp3 video-engine/public/audio/
rm -f "$REMOTION_OUT"

cd video-engine
xvfb-run -a npx remotion render ShortsVideo "../$REMOTION_OUT" \
  --codec h264 \
  --gl swangle \
  --concurrency 4 \
  --props src/scene-data.json \
  --headless=new \
  --chrome-mode chrome-for-testing \
  --browser-executable "../$BROWSER"
cd ..

ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$REMOTION_OUT" >/tmp/remotion_duration.txt
DUR=$(cat /tmp/remotion_duration.txt)
if [ -z "$DUR" ]; then
  echo "ERROR: Remotion output is not a valid video" >&2
  exit 1
fi

cp -f "$OUT" "$BACKUP"
mv -f "$REMOTION_OUT" "$OUT"
echo "OK: replaced $OUT with Remotion render, backup=$BACKUP, duration=${DUR}s"
