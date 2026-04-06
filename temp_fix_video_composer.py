
import os

filepath = r"d:\workspace\test\backend\services\video_composer.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Update import
old_import = "from backend.config import OUTPUT_DIR, VIDEO_WIDTH, VIDEO_HEIGHT, BASE_DIR"
new_import = "from backend.config import OUTPUT_DIR, VIDEO_WIDTH, VIDEO_HEIGHT, BASE_DIR, REMOTION_CODEC"
content = content.replace(old_import, new_import)

# Update render command
old_codec = '"--codec", "h264",'
new_codec = '"--codec", REMOTION_CODEC,\n                "--gl", "angle",'
content = content.replace(old_codec, new_codec)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Updates applied to video_composer.py")
