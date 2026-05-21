"""
Image Generator Service
Optimized for a clean, text-free visual storytelling format.
"""
import io
import hashlib
import shutil
import logging
import asyncio
import re
from pathlib import Path
from google import genai
from google.genai import types
from PIL import Image, ImageOps
from backend.config import (
    GOOGLE_GEMINI_API,
    OUTPUT_DIR,
)

CACHE_DIR = OUTPUT_DIR / "cache" / "images"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("shorts")
IMAGEN_MODEL = "gemini-2.5-flash-image"
_imagen_client = None


def get_imagen_client():
    global _imagen_client
    if _imagen_client is None:
        _imagen_client = genai.Client(api_key=GOOGLE_GEMINI_API)
    return _imagen_client


def save_shorts_frame(image_bytes: bytes, image_path: Path) -> None:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    frame = ImageOps.fit(
        image,
        (1080, 1920),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )
    frame.save(image_path, format="PNG", optimize=True)

STYLE_DNA = """
Art style: cute 2D animation illustration — clean bold outlines, flat cel-shading, round friendly shapes, warm cheerful tone.
Color palette: soft sky blue, warm peach, mint green, golden yellow, coral — bright and cheerful, high contrast for mobile.
Consistency: same line weight, same color temperature, same illustration density across all scenes like a single animated series.
"""

def sanitize_visual_text(value: str) -> str:
    clean = str(value or "")
    clean = re.sub(r"['\"“”‘’`]", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:500]


def build_structured_scene_prompt(
    *,
    visual_desc: str,
    scene_id: int,
    topic: str = "",
    situation: str = "",
    composition_mode: str = "vertical",
    visual_style: str = "cute-2d",
) -> str:
    topic_context = sanitize_visual_text(topic)
    situation_context = sanitize_visual_text(situation)
    composition_line = (
        "9:16 vertical composition, centered subject with generous breathing room, clean negative space, strong silhouette readability on mobile."
        if composition_mode == "vertical"
        else "1:1 square composition, centered focal hierarchy, self-contained subject framing, clean negative space, strong readability for overlay reuse."
    )

    if visual_style == "botero":
        style_dna = "[Style] Fernando Botero's style (Boterismo) — voluptuous exaggerated volume, extremely plump and bloated figures, smooth rounded shapes, clean outlines, flat oil painting aesthetic, rich warm colors, slightly whimsical and humorous tone. Every person, animal, and object in the scene must look inflated, round, and volumetric, as if painted by Fernando Botero. Drawn in a highly consistent manner so every scene looks like it belongs to the same collection."
        color_palette = "[Color Palette] Rich warm tones, soft sky blue, peach, mint green, coral, golden yellow. Bright and cheerful, good contrast for mobile. No dark muddy tones, no moody shadows, no muted desaturated palette."
        rendering_style = "[Rendering] Flat oil painting shading — clean uniform outlines, smooth rounded volumes, clean flat color fields. No photorealistic textures, no complex gradients, no digital glow overlays."
    else:
        # Default cute-2d
        style_dna = "[Style] Cute 2D animation illustration — bold clean outlines, flat cel-shading with soft pastel tones, round friendly shapes, warm and cheerful visual mood. Drawn in a consistent animated series style so every scene looks like it belongs to the same show."
        color_palette = "[Color Palette] Warm whites, soft sky blue, peach, mint green, coral, golden yellow. Bright and cheerful, good contrast for mobile. No dark muddy tones, no moody shadows, no muted desaturated palette."
        rendering_style = "[Rendering] Flat 2D animation style — bold uniform outlines, 2–3 tone cel shading, soft rounded highlights. No photorealistic textures, no painterly brush strokes, no complex gradients, no dreamy fog or glow overlays."

    return f"""{style_dna}
{color_palette}
[Subject] Build the entire frame around this visual idea from the script: {visual_desc}.
[Environment] Charming simplified scene environment with friendly background props, warm ambient lighting, clear subject-background separation. Topic: {topic_context}. Situation: {situation_context}.
[Composition] {composition_line}
{rendering_style}
[Consistency] Same line weight, same color temperature, same illustration density as the other scenes in this series — scene #{scene_id} of the same animated short.

[Hard Constraints]
- No readable text, letters, words, numbers, punctuation, labels, signs, logos, or fake writing anywhere.
- No photorealism, no 3D rendering, no dark gothic mood, no abstract expressionism, no painterly impressionist style.
- No dreamlike fog, no lens flare, no bokeh blur, no fantasy glowing effects.
- No presenter character, no teacher figure, no blackboard unless the topic literally requires it.
"""

async def generate_scene_image(
    scene: dict,
    job_dir: Path,
    topic: str = "",
    situation: str = "",
    log_callback: callable = None,
    visual_style: str = "cute-2d",
    **_kwargs,
) -> str:
    visual_desc = sanitize_visual_text(scene.get("background_description", "Relevant educational visual metaphor"))
    scene_id = scene.get("scene_id", 1)

    prompt = build_structured_scene_prompt(
        visual_desc=visual_desc,
        scene_id=scene_id,
        topic=topic,
        situation=situation,
        visual_style=visual_style,
    )

    hash_input = f"shorts_v3|{visual_style}|scene_{scene_id}|{visual_desc}|{topic}|{situation}"
    prompt_hash = hashlib.md5(hash_input.encode()).hexdigest()
    cached_path = CACHE_DIR / f"{prompt_hash}.png"

    if cached_path.exists():
        if log_callback: log_callback(f"✨ 장면 {scene_id}: 캐시 사용")
        image_path = job_dir / f"scene_{scene_id}.png"
        shutil.copy(cached_path, image_path)
        return str(image_path)

    max_retries = 5
    last_error = None
    for attempt in range(max_retries):
        try:
            if log_callback: log_callback(f"🎨 장면 {scene_id}: 이미지 생성 중... ({attempt+1})")
            response = await asyncio.to_thread(
                get_imagen_client().models.generate_content,
                model=IMAGEN_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=[types.Modality.IMAGE],
                ),
            )

            image_path = job_dir / f"scene_{scene_id}.png"
            for candidate in response.candidates or []:
                content = candidate.content
                for part in content.parts if content and content.parts else []:
                    if part.inline_data and part.inline_data.data:
                        save_shorts_frame(part.inline_data.data, image_path)
                        shutil.copy(image_path, cached_path)
                        return str(image_path)
            
            await asyncio.sleep(2)
        except Exception as e:
            last_error = e
            logger.warning(f"Scene {scene_id} generation error: {e}")
            await asyncio.sleep(5)
            
    raise Exception(f"Failed to generate image for scene {scene_id}: {last_error}")

async def generate_all_images(scenes: list[dict], job_dir: Path) -> list[str]:
    images_dir = job_dir / "images"
    images_dir.mkdir(exist_ok=True)
    return [await generate_scene_image(s, images_dir) for s in scenes]
