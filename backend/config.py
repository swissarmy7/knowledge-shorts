import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# API Keys
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
REMOTION_CONCURRENCY = int(os.getenv("REMOTION_CONCURRENCY", "8"))
REMOTION_CHROME_MODE = os.getenv("REMOTION_CHROME_MODE", "chrome-for-testing")
REMOTION_BROWSER_EXECUTABLE = os.getenv("REMOTION_BROWSER_EXECUTABLE", "").strip() or None

# Validate required non-GCP services. Imagen uses the AI Studio/Gemini API key path,
# and narration uses local Supertonic, so GCP service account settings are optional.
if not GOOGLE_GEMINI_API:
    raise ValueError("GOOGLE_GEMINI_API not set in .env")
if not ELEVENLABS_API_KEY:
    raise ValueError("ELEVENLABS_API_KEY not set in .env")
