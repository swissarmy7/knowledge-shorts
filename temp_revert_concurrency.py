
import os

filepath = r"d:\workspace\test\backend\services\video_composer.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Remove concurrency flag from the subprocess command
old_part = '"--concurrency", str(REMOTION_CONCURRENCY),'
content = content.replace(old_part, "")

# Keep the imports and codec for GPU acceleration
with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Concurrency limit removed from video_composer.py")
