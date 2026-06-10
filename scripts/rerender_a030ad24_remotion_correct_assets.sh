#!/usr/bin/env bash
set -euo pipefail
cd /var/www/html/my_shorts
JOB_ID="a030ad24"
OUT="output/shorts_${JOB_ID}.mp4"
BAD_REMOTION="output/shorts_${JOB_ID}.mixed-remotion.bad.mp4"
STATIC_BACKUP="output/shorts_${JOB_ID}.static-fallback.backup.mp4"
REMOTION_OUT="output/shorts_${JOB_ID}.correct-remotion.mp4"
BROWSER="video-engine/node_modules/.remotion/chrome-for-testing/linux-arm64/chrome-headless-shell-linux-arm64/chrome-headless-shell"

# Correct image responses for the a030ad24 Songjiho job. Do not use temp/, because it
# can be overwritten by newer jobs after a server restart.
declare -a IMAGES=(
  "output/cache/images/agy/0e7b1a44fa7df8c06dd7b1983ce6088c.png"
  "output/cache/images/agy/9b7cc35ef9a33435572170e614f4d439.png"
  "output/cache/images/agy/cb8a1b942b13b14cf8f55f102e895655.png"
  "output/cache/images/agy/2d07887bf61c38c5932e1ac4fd6f35a1.png"
  "output/cache/images/agy/cd85f74decd1cc079fa123852b3c61a5.png"
  "output/cache/images/agy/e8ad33655e841eff091f957dddc49428.png"
  "output/cache/images/agy/a280bd07a1ef5174371485391871eb88.png"
  "output/cache/images/agy/058f197987cb0b27822b6d2e0b7bcfd9.png"
)

for f in "${IMAGES[@]}" "$STATIC_BACKUP" "$BROWSER"; do
  if [ ! -e "$f" ]; then
    echo "ERROR: missing required file: $f" >&2
    exit 1
  fi
done

mkdir -p video-engine/public/images video-engine/public/audio
rm -f video-engine/public/images/scene_*.png video-engine/public/audio/narration_*.mp3 video-engine/public/full_narration.mp3
for i in "${!IMAGES[@]}"; do
  cp "${IMAGES[$i]}" "video-engine/public/images/scene_$((i+1)).png"
done

# Use the known-good static fallback's audio as one full narration track. This avoids
# relying on temp/<job>/audio, which may no longer belong to this job.
ffmpeg -y -i "$STATIC_BACKUP" -vn -acodec libmp3lame -q:a 2 video-engine/public/full_narration.mp3 >/dev/null 2>&1

python3 - <<'PY'
import json
from pathlib import Path
src = Path('video-engine/src/scene-data.json')
data = json.loads(src.read_text(encoding='utf-8'))
data['fullNarrationPath'] = 'full_narration.mp3'
for i, scene in enumerate(data['scenes'], start=1):
    scene['imagePath'] = f'images/scene_{i}.png'
    scene['audioPath'] = ''
Path('video-engine/src/scene-data.a030ad24.correct.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
PY

rm -f "$REMOTION_OUT"
cd video-engine
xvfb-run -a npx remotion render ShortsVideo "../$REMOTION_OUT" \
  --codec h264 \
  --gl swangle \
  --concurrency 4 \
  --props src/scene-data.a030ad24.correct.json \
  --headless=new \
  --chrome-mode chrome-for-testing \
  --browser-executable "../$BROWSER"
cd ..

DUR=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$REMOTION_OUT")
FPS=$(ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of default=noprint_wrappers=1:nokey=1 "$REMOTION_OUT")
if [ -z "$DUR" ] || [ "$FPS" != "30/1" ]; then
  echo "ERROR: invalid Remotion output duration=$DUR fps=$FPS" >&2
  exit 1
fi

cp -f "$OUT" "output/shorts_${JOB_ID}.pre-correct-rerender.backup.mp4"
mv -f "$REMOTION_OUT" "$OUT"
echo "OK: replaced $OUT with correct Remotion render, duration=${DUR}s fps=${FPS}"
echo "Backups: static=$STATIC_BACKUP mixed_bad=$BAD_REMOTION pre_correct=output/shorts_${JOB_ID}.pre-correct-rerender.backup.mp4"
