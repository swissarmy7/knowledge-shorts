"""Diagnostic script to test Remotion render and capture full output."""
import subprocess
import os

VIDEO_ENGINE_DIR = r"D:\workspace\test\video-engine"
OUTPUT_PATH = r"D:\workspace\test\output\diag_test.mp4"
PROPS_PATH = r"D:\workspace\test\video-engine\src\scene-data.json"
LOG_PATH = r"D:\workspace\test\output\remotion_diag.log"

cmd = f'npx remotion render ShortsVideo "{OUTPUT_PATH}" --codec h264 --props "{PROPS_PATH}" --log=verbose > "{LOG_PATH}" 2>&1'

print(f"Running: {cmd}")
result = os.system(f'cd /d "{VIDEO_ENGINE_DIR}" && {cmd}')
print(f"Exit code: {result}")
print(f"Log saved to: {LOG_PATH}")
