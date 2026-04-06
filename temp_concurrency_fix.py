
import os

filepath = r"d:\workspace\test\backend\services\video_composer.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Update import
old_import = "from backend.config import OUTPUT_DIR, VIDEO_WIDTH, VIDEO_HEIGHT, BASE_DIR, REMOTION_CODEC"
new_import = "from backend.config import OUTPUT_DIR, VIDEO_WIDTH, VIDEO_HEIGHT, BASE_DIR, REMOTION_CODEC, REMOTION_CONCURRENCY"
content = content.replace(old_import, new_import)

# Update render command
old_cmd_part = '"--log=verbose",'
new_cmd_part = '"--concurrency", str(REMOTION_CONCURRENCY),\n                "--log=verbose",'
content = content.replace(old_cmd_part, new_cmd_part)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Concurrency update applied to video_composer.py")
