import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# API Keys
# Gemini/Google generation has been replaced by host-side Codex workers.
# Keep the legacy env names readable for old .env files, but do not require or use them.
GOOGLE_GEMINI_API = os.getenv("GOOGLE_GEMINI_API")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
SUPER_TONE_API_KEY = os.getenv("SUPER_TONE_API_KEY")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

if not GOOGLE_CLOUD_PROJECT and GOOGLE_APPLICATION_CREDENTIALS:
    credentials_path = Path(GOOGLE_APPLICATION_CREDENTIALS)
    if not credentials_path.is_absolute():
        credentials_path = Path(__file__).parent.parent / credentials_path
    try:
        with credentials_path.open("r", encoding="utf-8") as f:
            GOOGLE_CLOUD_PROJECT = json.load(f).get("project_id")
    except Exception:
        GOOGLE_CLOUD_PROJECT = None

# Directories
BASE_DIR = Path(__file__).parent.parent  # project root (d:\workspace\test)
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = BASE_DIR / "temp"
UPLOADS_DIR = OUTPUT_DIR / "uploads"

# Create directories
OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)

# Video settings
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30
TARGET_DURATION = 60  # seconds (target around 1 minute)
REMOTION_CODEC = os.getenv("REMOTION_CODEC", "h264")
REMOTION_CONCURRENCY = int(os.getenv("REMOTION_CONCURRENCY", "2"))
REMOTION_GL = os.getenv("REMOTION_GL", "swangle")
REMOTION_CHROME_MODE = os.getenv("REMOTION_CHROME_MODE", "chrome-for-testing")
REMOTION_BROWSER_EXECUTABLE = os.getenv("REMOTION_BROWSER_EXECUTABLE", "").strip() or None
# Remotion can occasionally stop printing near the end while ffmpeg/compositor
# is still finalizing. video_composer monitors both final and temporary MP4
# growth before declaring a stall. Static FFmpeg fallback is intentionally gated
# elsewhere because it loses the Remotion title/subtitle layout.
REMOTION_RENDER_TIMEOUT = float(os.getenv("REMOTION_RENDER_TIMEOUT", "0"))
REMOTION_RENDER_STALL_TIMEOUT = float(os.getenv("REMOTION_RENDER_STALL_TIMEOUT", "300"))

# Image/text generation provider. Google/Gemini API calls are disabled; Codex is the default.
# IMAGE_PROVIDER=auto/google/agy are treated as codex for backwards-compatible .env files.
IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "codex")
AGY_IMAGE_TIMEOUT = float(os.getenv("AGY_IMAGE_TIMEOUT", "480"))
AGY_IMAGE_REQUEST_TIMEOUT = float(os.getenv("AGY_IMAGE_REQUEST_TIMEOUT", "600"))
AGY_IMAGE_POLL_INTERVAL = float(os.getenv("AGY_IMAGE_POLL_INTERVAL", "1.0"))
AGY_TEXT_TIMEOUT = float(os.getenv("AGY_TEXT_TIMEOUT", "300"))
AGY_TEXT_REQUEST_TIMEOUT = float(os.getenv("AGY_TEXT_REQUEST_TIMEOUT", "360"))
AGY_TEXT_POLL_INTERVAL = float(os.getenv("AGY_TEXT_POLL_INTERVAL", "1.0"))
SCRIPT_RESEARCH_ENABLED = os.getenv("SCRIPT_RESEARCH_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
SCRIPT_GENERATION_ATTEMPTS = max(1, int(os.getenv("SCRIPT_GENERATION_ATTEMPTS", "1")))

# Validate required non-GCP services. Generation now uses host-side Codex workers,
# and narration uses local Supertonic, so Gemini/GCP settings are optional.
if not ELEVENLABS_API_KEY:
    raise ValueError("ELEVENLABS_API_KEY not set in .env")
