"""
Image Generator Service
Optimized for a South Park inspired cartoon storytelling format.
"""
import hashlib
import json
import shutil
import logging
import asyncio
import re
import time
import uuid
from pathlib import Path
from PIL import Image
from backend.config import (
    OUTPUT_DIR,
    IMAGE_PROVIDER,
    AGY_IMAGE_TIMEOUT,
    AGY_IMAGE_REQUEST_TIMEOUT,
    AGY_IMAGE_POLL_INTERVAL,
)

CACHE_DIR = OUTPUT_DIR / "cache" / "images"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("shorts")


STYLE_DNA = """
Art style: polished Korean editorial illustration — clean cinematic composition, expressive human gestures, premium magazine-style digital painting, warm natural light, refined color palette.
Consistency: same recurring character, wardrobe, location, props, color temperature, and illustration density across all scenes like a single coherent story sequence.
"""

def sanitize_visual_text(value: str, max_len: int = 500) -> str:
    clean = str(value or "")
    clean = re.sub(r"['\"“”‘’`]", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:max_len]


def build_structured_scene_prompt(
    *,
    visual_desc: str,
    scene_id: int,
    topic: str = "",
    situation: str = "",
    composition_mode: str = "vertical",
    visual_style: str = "modern-editorial",
    visual_bible_context: str = "",
    full_story_arc: str = "",
) -> str:
    topic_context = sanitize_visual_text(topic)
    situation_context = sanitize_visual_text(situation)
    bible_context = sanitize_visual_text(visual_bible_context, max_len=1200)
    arc_context = sanitize_visual_text(full_story_arc, max_len=1800)
    composition_line = (
        "9:16 vertical composition, centered subject with generous breathing room, clean negative space, strong silhouette readability on mobile."
        if composition_mode == "vertical"
        else "1:1 square composition, centered focal hierarchy, self-contained subject framing, clean negative space, strong readability for overlay reuse."
    )

    if visual_style == "botero":
        style_dna = "[Style] Fernando Botero's style (Boterismo) — voluptuous exaggerated volume, extremely plump and bloated figures, smooth rounded shapes, clean outlines, flat oil painting aesthetic, rich warm colors, slightly whimsical and humorous tone. Every person, animal, and object in the scene must look inflated, round, and volumetric, as if painted by Fernando Botero. Drawn in a highly consistent manner so every scene looks like it belongs to the same collection."
        color_palette = "[Color Palette] Rich warm tones, soft sky blue, peach, mint green, coral, golden yellow. Bright and cheerful, good contrast for mobile. No dark muddy tones, no moody shadows, no muted desaturated palette."
        rendering_style = "[Rendering] Flat oil painting shading — clean uniform outlines, smooth rounded volumes, clean flat color fields. No photorealistic textures, no complex gradients, no digital glow overlays."
    elif visual_style == "webtoon-cinematic":
        style_dna = "[Style] Premium Korean webtoon cinematic cutscene — dramatic but clean line art, expressive faces and gestures, soft painterly cel shading, polished episode key art quality. Every scene must look like consecutive panels from the same high-end Korean webtoon sequence."
        color_palette = "[Color Palette] Cohesive cinematic colors, warm natural highlights, controlled shadows, refined accent colors. Good contrast for mobile, no muddy gray palette, no neon clutter."
        rendering_style = "[Rendering] High-quality webtoon illustration — clean ink lines, painterly cel shading, controlled depth, clear subject hierarchy. No photorealism, no 3D render, no flat icon style."
    elif visual_style == "south-park-comic":
        style_dna = "[Style] South Park inspired flat cutout cartoon style — simple geometric characters, round eyes, thick black outlines, paper cutout look, bold primary colors, exaggerated funny expressions, satirical TV cartoon composition."
        color_palette = "[Color Palette] Bright flat colors, clean high contrast, simple backgrounds, readable mobile composition."
        rendering_style = "[Rendering] Flat 2D cutout cartoon, no photorealism, no 3D render, no painterly shading. Korean speech bubbles, signs, labels, phone screens, map labels, or short captions are allowed when useful; keep any text large, legible, and limited to one or two short Korean phrases."
    elif visual_style == "irasutoya" or visual_style == "ssul-shorts":
        style_dna = "[Style] Polished Korean editorial illustration — clean cinematic composition, expressive human gestures, premium magazine-style digital painting, warm natural light, refined color palette. Not an icon pack; every frame is a complete story scene."
        color_palette = "[Color Palette] Refined warm neutrals with a small set of consistent accent colors. Mobile-friendly contrast, no muddy tones, no neon clutter."
        rendering_style = "[Rendering] Premium editorial digital illustration — soft painterly shading, clean shapes, realistic but stylized proportions, clear subject-background separation. No photorealism, no 3D render, no flat clipart."
    else:
        style_dna = "[Style] South Park inspired flat cutout cartoon style — simple geometric characters, round eyes, thick black outlines, paper cutout look, bold primary colors, exaggerated funny expressions, satirical TV cartoon composition."
        color_palette = "[Color Palette] Bright flat colors, clean high contrast, simple backgrounds, readable mobile composition."
        rendering_style = "[Rendering] Flat 2D cutout cartoon, no photorealism, no 3D render, no painterly shading. Korean speech bubbles, signs, labels, phone screens, map labels, or short captions are allowed when useful; keep any text large, legible, and limited to one or two short Korean phrases."

    prompt = f"""{style_dna}
{color_palette}
[Global Story Bible — obey before the local scene] {bible_context}
[Full Narrative Sequence — this scene must align with the whole short] {arc_context}
[Subject] Build the entire frame around this local scene action: {visual_desc}.
[Environment] Use the same world, wardrobe, character design, recurring props, and location established in the Story Bible. Topic: {topic_context}. Situation: {situation_context}.
[Composition] {composition_line}
{rendering_style}
[Consistency] Same line weight, same color temperature, same illustration density as the other scenes in this series — scene #{scene_id} of the same animated short.

[Hard Constraints]
- Korean speech bubbles, signs, map labels, phone-screen text, and short captions are allowed; keep them large, legible, and limited to one or two short phrases.
- No photorealism, no 3D rendering, no dark gothic mood, no abstract expressionism, no painterly impressionist style.
- No dreamlike fog, no lens flare, no bokeh blur, no fantasy glowing effects.
- No presenter character, no teacher figure, no blackboard unless the topic literally requires it.
- Never change a recurring character's outfit, age, hairstyle, body type, location, or key props between scenes unless the Full Narrative Sequence explicitly says it changed.
- If the topic implies a specific setting or dress code, keep it consistent in every relevant scene, e.g. funeral etiquette means black mourning clothes inside the same funeral hall, never random hanbok or casual bright clothing.
"""
    if visual_style in ["irasutoya", "ssul-shorts"]:
        prompt += "\n--ar 9:16"
    return prompt


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _sanitize_output_rel(output_rel: str) -> str:
    """Remove any .. path traversal components from a relative path."""
    parts = [p for p in Path(output_rel).parts if p not in ("..", ".")]
    return str(Path(*parts)) if parts else ""


# ---------------------------------------------------------------------------
# Codex image helper functions (called by worker roundtrip and tests)
# ---------------------------------------------------------------------------

def build_agy_image_request(prompt: str, output_rel: str, request_id: str) -> dict:
    clean_rel = _sanitize_output_rel(output_rel)
    return {
        "request_id": request_id,
        "prompt": prompt,
        "output_rel": clean_rel,
        "output_container_path": str(OUTPUT_DIR / clean_rel),
        "codex_timeout_sec": AGY_IMAGE_TIMEOUT,
        # Kept for compatibility with older workers that may still be running.
        "agy_timeout_sec": AGY_IMAGE_TIMEOUT,
    }


def write_agy_image_request(
    prompt: str, output_rel: str, request_id: str
) -> tuple[Path, Path]:
    agy_dir = OUTPUT_DIR / "agy_requests"
    agy_dir.mkdir(parents=True, exist_ok=True)
    payload = build_agy_image_request(prompt, output_rel, request_id)
    req_path = agy_dir / f"{request_id}.request.json"
    res_path = agy_dir / f"{request_id}.response.json"
    req_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return req_path, res_path


def resolve_agy_response_image(response: dict) -> Path:
    if response.get("status") != "ok":
        raise ValueError(f"codex image error: {response.get('error', 'unknown')}")
    output_rel = response.get("output_rel", "")
    img_path = OUTPUT_DIR / output_rel
    if not img_path.exists():
        raise FileNotFoundError(f"agy output image not found: {img_path}")
    return img_path


# ---------------------------------------------------------------------------
# Codex async path
# ---------------------------------------------------------------------------

async def generate_scene_image_agy(
    scene: dict,
    job_dir: Path,
    topic: str = "",
    situation: str = "",
    log_callback: callable = None,
    visual_style: str = "modern-editorial",
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
        visual_bible_context=scene.get("visual_bible_context", ""),
        full_story_arc=scene.get("full_story_arc", ""),
    )

    # Normal generation can use the deterministic cache, but a fresh final-video
    # image-prep job must not resurrect stale images from a previous run. The
    # backend passes _image_batch_id for those jobs so the cache/output key is
    # scoped to this specific generation batch.
    image_batch_id = str(scene.get("_image_batch_id") or "")
    hash_input = f"shorts_v5|codex|batch={image_batch_id}|{visual_style}|scene_{scene_id}|{visual_desc}|{topic}|{situation}|{scene.get('visual_bible_context','')}|{scene.get('full_story_arc','')}"
    prompt_hash = hashlib.md5(hash_input.encode()).hexdigest()
    codex_cache_dir = CACHE_DIR / "codex"
    cached_path = codex_cache_dir / f"{prompt_hash}.png"

    if cached_path.exists():
        if log_callback:
            log_callback(f"✨ 장면 {scene_id}: codex 캐시 사용")
        image_path = job_dir / f"scene_{scene_id}.png"
        shutil.copy(cached_path, image_path)
        return str(image_path)

    # Keep the cache filename deterministic, but make the transport request ID
    # unique. The worker directory intentionally keeps old *.response.json files
    # for debugging; reusing a deterministic request_id can make a fresh request
    # read a stale response before the worker processes the new request.
    request_id = f"scene{scene_id}-{prompt_hash[:12]}-{uuid.uuid4().hex[:6]}"
    output_rel = f"cache/images/codex/{prompt_hash}.png"

    req_path, res_path = write_agy_image_request(
        prompt=prompt,
        output_rel=output_rel,
        request_id=request_id,
    )

    if log_callback:
        log_callback(f"🎨 장면 {scene_id}: codex 이미지 요청 중...")

    deadline = time.monotonic() + AGY_IMAGE_REQUEST_TIMEOUT
    while time.monotonic() < deadline:
        if res_path.exists():
            break
        await asyncio.sleep(AGY_IMAGE_POLL_INTERVAL)
    else:
        req_path.unlink(missing_ok=True)
        raise TimeoutError(f"codex image timeout for scene {scene_id} (request_id={request_id})")

    response = json.loads(res_path.read_text(encoding="utf-8"))
    img_path = resolve_agy_response_image(response)

    image_path = job_dir / f"scene_{scene_id}.png"
    codex_cache_dir.mkdir(parents=True, exist_ok=True)
    image = Image.open(img_path).convert("RGB")
    image.save(image_path, format="PNG", optimize=True)
    image.save(cached_path, format="PNG", optimize=True)
    return str(image_path)


# ---------------------------------------------------------------------------
# Public dispatch
# ---------------------------------------------------------------------------

async def generate_scene_image(
    scene: dict,
    job_dir: Path,
    topic: str = "",
    situation: str = "",
    log_callback: callable = None,
    visual_style: str = "modern-editorial",
    **_kwargs,
) -> str:
    provider = IMAGE_PROVIDER
    if provider not in {"codex", "agy", "auto", "google"}:
        logger.warning(f"Unknown IMAGE_PROVIDER={provider!r}; using codex")
    elif provider in {"agy", "auto", "google"}:
        logger.info(f"IMAGE_PROVIDER={provider!r} is mapped to codex; Gemini image API is disabled")

    return await generate_scene_image_agy(
        scene, job_dir, topic=topic, situation=situation,
        log_callback=log_callback, visual_style=visual_style,
    )


async def generate_all_images(scenes: list[dict], job_dir: Path) -> list[str]:
    images_dir = job_dir / "images"
    images_dir.mkdir(exist_ok=True)
    return [await generate_scene_image(s, images_dir) for s in scenes]
