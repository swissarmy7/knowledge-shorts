import os
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

# Validate
if not GOOGLE_GEMINI_API:
    raise ValueError("GOOGLE_GEMINI_API not set in .env")
if not ELEVENLABS_API_KEY:
    raise ValueError("ELEVENLABS_API_KEY not set in .env")
if not GOOGLE_APPLICATION_CREDENTIALS:
    raise ValueError("GOOGLE_APPLICATION_CREDENTIALS not set in .env")
