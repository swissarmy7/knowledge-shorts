"""
Image Generator Service
Uses Gemini API to generate scene images.
"""
import io
import uuid
import hashlib
import shutil
import logging
import asyncio
import re
from pathlib import Path
from google import genai
from google.genai import types
from backend.config import GOOGLE_GEMINI_API, TEMP_DIR, OUTPUT_DIR

# Global image cache directory
CACHE_DIR = OUTPUT_DIR / "cache" / "images"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("shorts")
client = genai.Client(api_key=GOOGLE_GEMINI_API)

# Style DNA: Strictly maintain the original 2D Vector Animation art style
STYLE_DNA = """
Art style: Professional flat 2D educational vector animation.
Visual style: Clean vector illustration, solid color fills, minimal thin outlines. 
Aesthetic: Similar to modern educational YouTube channels (e.g., Kurzgesagt style but simpler).
Color palette: Soft pastel colors, warm harmonious tones.
Lighting: Even soft lighting, no realistic shadows, no 3D rendering.
Composition: Character clearly centered in frame, simple background.
"""

MOTION_PROMPTS = {
    "talking": "pleasant facial expression with mouth slightly open as if speaking, looking at viewer, one hand raised naturally",
    "pointing": "right index finger pointing forward, direct eye contact, confident illustration",
    "thinking": "finger on chin, looking upward with a thoughtful expression, clean portrait",
    "jumping": "both feet off the ground, arms raised in excitement, joyful flat vector",
    "surprised": "wide eyes, open mouth, hands near face in a shocked yet educational style",
    "zoom_in": "close-up portrait framing, focused on facial features",
    "zoom_out": "full body illustration, wide flat vector composition",
    "slide": "side view, walking pose with a natural stride, one leg forward",
    "fade": "front-facing neutral pose, hands relaxed at sides",
    "bounce": "slight crouch, ready to move, dynamic flat vector energy",
}

async def generate_scene_image(
    scene: dict, job_dir: Path, topic: str = "", situation: str = ""
) -> str:
    """Generate an image for a single scene with retry logic."""
    char_desc = scene.get("character_description", "A friendly character")
    bg_desc = scene.get("background_description", "A simple clean setting")
    script_context = scene.get("script", "")
    motion = scene.get("motion", "talking")
    motion_prompt = MOTION_PROMPTS.get(motion, MOTION_PROMPTS["talking"])

    # Model Selection: Reverted to fast/cost-effective model as requested
    IMAGEN_MODEL = "models/imagen-4.0-fast-generate-001"

    prompt = f"""[VISUAL_IDENTITY]
- Character: {char_desc}
- REQUIRED: Consistency is paramount. Maintain exactly the same face, hair, and clothing across scenes.
- Environment: {bg_desc}
- Action/Pose: {motion_prompt}

[CHARACTER_VISUAL_CONSTRAINT]
- Age: 20s or early 30s only. 
- FORBIDDEN: Gray hair, white hair, receding hairline, wrinkles, saggy skin, old-man (grandpa) features.
- REQUIRED: Youthful skin, vibrant natural hair color, modern trendy hairstyle, energetic posture.
- Attire: Modern, stylish, and youthful professional look.

[STRICT_STYLE_GUIDE]
{STYLE_DNA}
- Orientation: Vertical portrait (9:16 aspect ratio).
- Composition: Exactly ONE character, centered and clear.

[CORE_VISUAL_COMMANDS]
- The scene is inspired by a topic related to: "{topic[:100]}".
- Strictly NO speech bubbles.
- Strictly NO dialogue boxes.
- Strictly NO text, NO labels, NO signs, NO words.
- The image must be 100% PURE VISUAL with zero written elements.
- Professional 2D flat vector art only. No 3D, No complex shadows.
"""

    logger.info(f"DEBUG: Final Prompt for hashing (fragment): '{prompt[:100]}...'")
    prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
    cached_path = CACHE_DIR / f"{prompt_hash}.png"

    # Check cache first
    if cached_path.exists():
        logger.info(f"✨ Image cache hit for scene {scene.get('scene_id')}! Reusing: {cached_path.name}")
        image_filename = f"scene_{scene.get('scene_id', uuid.uuid4().hex)}.png"
        image_path = job_dir / image_filename
        shutil.copy(cached_path, image_path)
        return str(image_path)

    max_retries = 10
    retry_delay = 2.0
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Generating image for scene {scene.get('scene_id')} (Attempt {attempt + 1}/{max_retries})...")
            response = client.models.generate_images(
                model=IMAGEN_MODEL,
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="9:16",
                ),
            )

            image_filename = f"scene_{scene.get('scene_id', uuid.uuid4().hex)}.png"
            image_path = job_dir / image_filename

            if response.generated_images:
                image_data = response.generated_images[0].image
                image_data.save(str(image_path))
                
                try:
                    shutil.copy(image_path, cached_path)
                    logger.info(f"💾 Saved image to global cache: {cached_path.name}")
                except Exception as e:
                    logger.warning(f"Failed to save to cache: {e}")
                    
                return str(image_path)
            
            logger.warning(f"Scene {scene.get('scene_id')} AI generated empty result. Retrying...")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
                
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Scene {scene.get('scene_id')} generation error: {error_msg}")
            
            if attempt < max_retries - 1:
                wait_time = retry_delay
                if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
                    match = re.search(r"retryDelay':\s*'(\d+)s'", error_msg)
                    if match:
                        wait_time = int(match.group(1)) + 1
                    else:
                        wait_time = max(wait_time, 15.0)
                
                await asyncio.sleep(wait_time)
                retry_delay *= 2
            else:
                logger.error(f"Scene {scene.get('scene_id')} failed after {max_retries} attempts.")
                raise Exception(f"Failed to generate image for scene {scene.get('scene_id')}. Last error: {error_msg}")

async def generate_all_images(scenes: list[dict], job_dir: Path) -> list[str]:
    """Generate images for all scenes."""
    images_dir = job_dir / "images"
    images_dir.mkdir(exist_ok=True)

    image_paths = []
    for scene in scenes:
        path = await generate_scene_image(scene, images_dir)
        image_paths.append(path)

    return image_paths
