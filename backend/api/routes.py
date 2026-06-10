"""
API Routes for the Shorts Generator
"""
import uuid
import asyncio
import logging
import shutil
import time
import math
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from backend.config import (
    TEMP_DIR,
    OUTPUT_DIR,
    UPLOADS_DIR,
    VIDEO_FPS,
    AGY_IMAGE_POLL_INTERVAL,
    AGY_IMAGE_REQUEST_TIMEOUT,
)
from backend.services.history_store import (
    build_history_entry,
    delete_history_entry,
    get_history_entry,
    list_history_entries,
    save_history_entry,
)
from backend.services.script_generator import (
    generate_script,
    generate_metadata_from_script,
    enrich_script_metadata,
    sanitize_scene_scripts,
    apply_visual_continuity_context,
)
from backend.services.image_generator import (
    CACHE_DIR,
    build_structured_scene_prompt,
    resolve_agy_response_image,
    sanitize_visual_text,
    write_agy_image_request,
)
from backend.services.narration_generator import generate_all_narrations, generate_narration, get_audio_duration
from backend.services.subtitle_generator import generate_subtitles
from backend.services.video_composer import compose_video
from backend.services.youtube_uploader import upload_video
from backend.services.auth_service import (
    create_access_token, verify_password, MASTER_PASSWORD_HASH, 
    get_current_user, is_auth_enabled, LoginRequest, Token
)

logger = logging.getLogger("shorts")
logging.basicConfig(level=logging.INFO)

router = APIRouter(prefix="/api", tags=["shorts"])

# In-memory job store
jobs: dict[str, dict] = {}

VIDEO_ACTIVE_STATUSES = {
    "pending",
    "generating_images",
    "generating_narration",
    "composing_video",
}
SCRIPT_ACTIVE_STATUSES = {"generating_script"}


def _is_video_job(job: dict) -> bool:
    """Return True for current and legacy video jobs.

    Older in-memory jobs may not have job_type, so infer video jobs from
    statuses that only the video pipeline uses.
    """
    job_type = job.get("job_type")
    if job_type:
        return job_type == "video"
    return job.get("status") in VIDEO_ACTIVE_STATUSES


def _find_active_video_job() -> Optional[dict]:
    """Find the currently running final-video job, if any."""
    for job_id, job in jobs.items():
        if _is_video_job(job) and job.get("status") in VIDEO_ACTIVE_STATUSES:
            return {"job_id": job_id, **job}
    return None


def _can_start_video_job() -> tuple[bool, Optional[dict]]:
    active_job = _find_active_video_job()
    return active_job is None, active_job


def _apply_scene_duration_cap(
    scenes: list[dict],
    duration_target: Optional[dict],
    pause_seconds: float = 0.4,
) -> float:
    """Keep the rendered scene timeline within the shorts cap.

    Video duration is the sum of scene durations, not just raw audio length.
    We therefore distribute a bounded per-scene pause only if it fits under
    the configured maximum, capped at 60 seconds overall.
    """
    if not scenes:
        return 0.0

    max_total = min(float((duration_target or {}).get("max_seconds") or 60.0), 60.0)
    audio_total = sum(float(scene.get("audio_duration", scene.get("duration", 0.0)) or 0.0) for scene in scenes)
    remaining = max(0.0, max_total - audio_total)
    per_scene_pause = min(pause_seconds, remaining / len(scenes)) if scenes else 0.0

    total_duration = 0.0
    for scene in scenes:
        audio_duration = float(scene.get("audio_duration", scene.get("duration", 0.0)) or 0.0)
        scene["duration"] = audio_duration + per_scene_pause
        total_duration += scene["duration"]

    max_frames = int(max_total * VIDEO_FPS)
    total_frames = sum(math.ceil(float(scene.get("duration") or 0.0) * VIDEO_FPS) for scene in scenes)
    overflow_frames = total_frames - max_frames
    if overflow_frames > 0:
        trim_seconds = overflow_frames / VIDEO_FPS
        last_scene = scenes[-1]
        min_last_duration = float(last_scene.get("audio_duration", 0.0) or 0.0)
        last_scene["duration"] = max(min_last_duration, float(last_scene.get("duration") or 0.0) - trim_seconds)
        total_duration = sum(float(scene.get("duration") or 0.0) for scene in scenes)

    return total_duration


async def _cleanup_old_files_safe():
    """Non-blocking wrapper: run cleanup in a thread pool so the event loop is never blocked."""
    await asyncio.to_thread(cleanup_old_files)


def cleanup_old_files():
    """Clean transient temp files only.
    Generated videos are preserved for the history board.
    """
    logger.info("Cleaning up transient temp files...")

    # DO NOT clean output MP4 files here.
    # They are now used by the persistent history board.
    # DO NOT clean uploads directory here either.
    # User-uploaded images (output/uploads/) are needed by compose_video().

    TEMP_DIR.mkdir(exist_ok=True)

    # Do not wipe the whole temp root. A retry can overlap with an in-flight job,
    # and deleting the shared temp tree kills the running narration/render step.
    active_job_ids = {
        job_id for job_id, job in jobs.items()
        if job.get("status") in {"pending", "generating_images", "generating_narration", "composing_video"}
    }
    cutoff = time.time() - (12 * 60 * 60)

    for child in TEMP_DIR.iterdir():
        if not child.is_dir():
            continue
        if child.name in active_job_ids:
            continue
        try:
            if child.stat().st_mtime < cutoff:
                shutil.rmtree(child, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Could not clean temp job directory {child}: {e}")


def _output_relative_path(path: Path) -> Optional[str]:
    try:
        return str(path.resolve().relative_to(OUTPUT_DIR.resolve()))
    except Exception:
        return None


def _resolve_scene_main_image(scene: dict) -> Optional[str]:
    """Return an existing user/AI-selected scene image path, if present.

    The editor stores manually uploaded or per-scene AI generated images as
    image overlays (usually ``uploads/...``). When the user clicks the final
    video button, those approved images should become the scene's main visual
    source instead of triggering a brand-new background image generation pass.
    """
    candidates = []

    for key in ("image_path", "generated_image_path", "asset_path"):
        value = scene.get(key)
        if value:
            candidates.append(str(value))

    for overlay in scene.get("overlays", []) or []:
        if overlay.get("type") == "image" and overlay.get("content"):
            candidates.append(str(overlay.get("content")))

    for raw in candidates:
        rel = raw.strip()
        if not rel:
            continue
        if rel.startswith("/output/"):
            rel = rel[len("/output/"):]
        elif rel.startswith("output/"):
            rel = rel[len("output/"):]

        path = Path(rel)
        abs_path = path if path.is_absolute() else OUTPUT_DIR / rel
        if abs_path.exists() and abs_path.is_file():
            return str(abs_path)

    return None


def _clear_scene_generated_images(script_data: dict) -> None:
    """Remove generated scene images before a fresh image job.

    A new final-video attempt must not reuse stale image paths or image overlays
    left from a previous browser/job state. Text/annotation overlays are kept;
    only visual source image references are removed.
    """
    script_data.pop("image_job_id", None)
    script_data.pop("images_ready_for_final", None)
    for scene in script_data.get("scenes", []) or []:
        for key in ("image_path", "generated_image_path", "asset_path"):
            scene.pop(key, None)
        overlays = []
        for overlay in scene.get("overlays", []) or []:
            if overlay.get("type") == "image":
                continue
            overlays.append(overlay)
        scene["overlays"] = overlays


class GenerateRequest(BaseModel):
    topic: str
    tags: list[str] = []
    direction: str = ""
    style: str = "star-instructor"  # star-instructor or ssul-shorts
    scene_count: int = 12  # 8, 10, or 12
    visual_style: str = "south-park-comic"
    voice_gender: Optional[str] = "여성"
    voice_age: Optional[str] = "청년"
    voice_tone: Optional[str] = "차분하게"
    voice_speed: Optional[str] = "1.05"


class VideoGenerateRequest(BaseModel):
    script_data: dict


class SceneImagesGenerateRequest(BaseModel):
    script_data: dict
    force_new: bool = False


class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: int
    message: str = ""
    logs: list[str] = []
    job_type: Optional[str] = None
    video_url: Optional[str] = None
    script_data: Optional[dict] = None
    history_id: Optional[str] = None


class YouTubeUploadRequest(BaseModel):
    job_id: str
    title: str
    description: str
    tags: list[str] = []


class HistoryItem(BaseModel):
    id: str
    job_id: str
    created_at: str
    topic: str = ""
    subject: str = ""
    video_title: str = ""
    youtube_title: str = ""
    youtube_description: str = ""
    youtube_tags: list[str] = []
    situation: str = ""
    scene_count: int = 0
    video_url: str
    script_data: Optional[dict] = None


@router.post("/login", response_model=Token)
async def login(req: LoginRequest):
    if not is_auth_enabled():
        # If no password is set in .env, just allow login with any password (for initial setup)
        # But normally we'd force setting a password.
        access_token = create_access_token(data={"sub": "admin"})
        return {"access_token": access_token, "token_type": "bearer"}
    
    if not verify_password(req.password, MASTER_PASSWORD_HASH):
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="비밀번호가 틀렸습니다.",
        )
    
    access_token = create_access_token(data={"sub": "admin"})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/auth-check")
async def auth_check(current_user: str = Depends(get_current_user)):
    return {"status": "authenticated", "user": current_user}


async def run_script_pipeline(job_id: str, req: GenerateRequest):
    """Run slow Codex script generation in the background so HTTPS/proxy timeouts do not abort the UI request."""
    try:
        jobs[job_id].update({
            "status": "generating_script",
            "progress": 20,
            "message": "🧠 codex로 대본 기획 중...",
        })
        script_data = await generate_script(
            req.topic,
            req.tags,
            req.direction,
            req.style,
            req.scene_count,
            req.visual_style,
            voice_gender=req.voice_gender,
            voice_age=req.voice_age,
            voice_tone=req.voice_tone,
            voice_speed=req.voice_speed,
        )
        jobs[job_id].update({
            "status": "script_ready",
            "progress": 100,
            "message": "✅ 대본 생성 완료",
            "script_data": script_data,
        })
        logger.info(f"[{job_id}] Script Generation Completed")
    except Exception as e:
        logger.error(f"[{job_id}] Script Generation Failed: {str(e)}")
        jobs[job_id].update({
            "status": "error",
            "progress": 0,
            "message": f"스크립트 생성 실패: {e}",
        })


@router.post("/generate-script")
async def start_script_generation(req: GenerateRequest, background_tasks: BackgroundTasks, current_user: str = Depends(get_current_user)):
    """Start script generation asynchronously (Step 1 of the interactive pipeline)."""
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "generating_script",
        "job_type": "script",
        "progress": 10,
        "message": "🧠 대본 생성 작업 시작...",
        "logs": [],
        "script_data": None,
    }

    logger.info(f"[{job_id}] Script Generation Job queued: topic='{req.topic}', visual_style='{req.visual_style}'")
    background_tasks.add_task(run_script_pipeline, job_id, req)
    return {"job_id": job_id, "status": "generating_script"}


class MetadataRequest(BaseModel):
    script_text: str
    situation: str = ""


@router.post("/generate-metadata")
async def generate_metadata(req: MetadataRequest, current_user: str = Depends(get_current_user)):
    """Generate YouTube metadata (title, description, tags) from user-written script."""
    logger.info(f"[Metadata] Generating metadata from manual script")
    
    try:
        metadata = await generate_metadata_from_script(req.script_text, req.situation)
        return {"status": "ok", "metadata": metadata}
    except Exception as e:
        logger.error(f"[Metadata] Generation failed: {str(e)}")
        return {"error": str(e)}


@router.post("/upload-asset")
async def upload_asset(file: UploadFile = File(...), current_user: str = Depends(get_current_user)):
    """Upload a custom image for a scene."""
    file_ext = Path(file.filename).suffix
    unique_filename = f"{uuid.uuid4().hex}{file_ext}"
    file_path = UPLOADS_DIR / unique_filename
    
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Return relative path for use in schema
    return {"path": f"uploads/{unique_filename}"}


class OverlayImageRequest(BaseModel):
    prompt: str
    scene_script: str = ""  # Optional: scene context for better generation
    visual_style: str = "south-park-comic"


@router.post("/generate-image")
async def generate_overlay_image(req: OverlayImageRequest, current_user: str = Depends(get_current_user)):
    """Generate an AI illustration image for use as an overlay via Codex."""

    safe_prompt = sanitize_visual_text(req.prompt)
    scene_context = sanitize_visual_text(req.scene_script)
    illustration_prompt = build_structured_scene_prompt(
        visual_desc=safe_prompt,
        scene_id=0,
        topic=safe_prompt,
        situation=scene_context,
        composition_mode="square",
        visual_style=req.visual_style,
    ) + """
[Overlay Specific]
- Generate the main visual idea as a clean isolated square-friendly composition for reuse as an overlay asset.
- Keep the composition centered and self-contained.
- The result must feel like a polished editorial illustration, not a flat icon pack or photoreal movie still.
"""

    import hashlib
    prompt_hash = hashlib.md5(f"overlay_codex_v1|{req.visual_style}|{illustration_prompt}".encode()).hexdigest()
    cached_path = CACHE_DIR / "codex" / f"overlay_{prompt_hash}.png"

    if cached_path.exists():
        logger.info(f"[AI Image] codex cache hit for overlay: {cached_path.name}")
        unique_filename = f"cached_{uuid.uuid4().hex}.png"
        file_path = UPLOADS_DIR / unique_filename
        shutil.copy(cached_path, file_path)
        return {"path": f"uploads/{unique_filename}"}

    request_id = f"overlay-{prompt_hash[:12]}"
    output_rel = f"cache/images/codex/overlay_{prompt_hash}.png"
    req_path, res_path = write_agy_image_request(
        prompt=illustration_prompt,
        output_rel=output_rel,
        request_id=request_id,
    )
    logger.info(f"[AI Image] Requested codex overlay image: {request_id}")

    deadline = time.monotonic() + AGY_IMAGE_REQUEST_TIMEOUT
    while time.monotonic() < deadline:
        if res_path.exists():
            break
        await asyncio.sleep(AGY_IMAGE_POLL_INTERVAL)
    else:
        req_path.unlink(missing_ok=True)
        return {"error": f"이미지 생성 시간 초과: codex worker 응답 없음 ({request_id})"}

    try:
        import json
        response = json.loads(res_path.read_text(encoding="utf-8"))
        generated_path = resolve_agy_response_image(response)
        unique_filename = f"{uuid.uuid4().hex}.png"
        file_path = UPLOADS_DIR / unique_filename
        shutil.copy(generated_path, file_path)
        logger.info(f"[AI Image] Generated codex overlay image: {file_path}")
        return {"path": f"uploads/{unique_filename}"}
    except Exception as e:
        logger.error(f"[AI Image] codex overlay generation failed: {e}")
        return {"error": f"이미지 생성 오류: {e}"}


class SceneImageRequest(BaseModel):
    scene: dict
    script_data: dict = {}
    visual_style: str = "south-park-comic"


@router.post("/generate-scene-image")
async def generate_main_scene_image(req: SceneImageRequest, current_user: str = Depends(get_current_user)):
    """Generate one full-scene vertical image and return a persistent output-relative path."""
    from backend.services.image_generator import generate_scene_image

    scene = dict(req.scene or {})
    script_data = req.script_data or {}
    visual_style = req.visual_style or script_data.get("visual_style", "south-park-comic")

    video_title_meta = script_data.get("video_title", {})
    if isinstance(video_title_meta, dict):
        topic_context = f"{video_title_meta.get('highlight', '')} {video_title_meta.get('rest', '')}".strip()
    else:
        topic_context = str(video_title_meta or "")
    situation_context = (script_data.get("situation_setting") or {}).get("situation", "")

    scene_id = scene.get("scene_id", scene.get("sceneId", 1)) or 1
    request_job_id = f"interactive_{uuid.uuid4().hex[:8]}"
    job_dir = TEMP_DIR / request_job_id / "images"
    job_dir.mkdir(parents=True, exist_ok=True)

    characters = script_data.get("characters", []) or []
    char_id = scene.get("character_id", "char_1")
    char_meta = next((c for c in characters if c.get("id") == char_id), {})
    enriched_scene = {
        **scene,
        "character_description": char_meta.get("description", "A character"),
    }

    try:
        generated_path = await generate_scene_image(
            enriched_scene,
            job_dir,
            topic=topic_context,
            situation=situation_context,
            visual_style=visual_style,
        )
        persistent_dir = OUTPUT_DIR / "cache" / "images" / "interactive"
        persistent_dir.mkdir(parents=True, exist_ok=True)
        persistent_path = persistent_dir / f"scene_{scene_id}_{uuid.uuid4().hex[:10]}.png"
        shutil.copy2(generated_path, persistent_path)
        rel = _output_relative_path(persistent_path)
        if not rel:
            raise RuntimeError("generated image path is outside output directory")
        return {"status": "ok", "path": rel}
    except Exception as e:
        logger.error(f"[SceneImage] generation failed: {e}", exc_info=True)
        return {"error": f"장면 이미지 생성 실패: {e}"}


async def run_scene_images_pipeline(job_id: str, script_data: dict, job_dir: Path, force_new: bool = False):
    """Generate missing scene images as a background job and persist paths into script_data."""
    try:
        sanitize_scene_scripts(script_data)
        if force_new:
            _clear_scene_generated_images(script_data)
        apply_visual_continuity_context(
            script_data,
            topic=script_data.get("topic", "") or script_data.get("subject", ""),
            direction=(script_data.get("situation_setting") or {}).get("situation", ""),
        )
        scenes = script_data.get("scenes", []) or []
        num_scenes = len(scenes)
        visual_style = script_data.get("visual_style", "south-park-comic")
        characters_list = script_data.get("characters", []) or []
        char_lookup = {c.get("id"): c for c in characters_list if c.get("id")}

        video_title_meta = script_data.get("video_title", {})
        if isinstance(video_title_meta, dict):
            topic_context = f"{video_title_meta.get('highlight', '')} {video_title_meta.get('rest', '')}".strip()
        else:
            topic_context = str(video_title_meta or "")
        situation_context = (script_data.get("situation_setting") or {}).get("situation", "")

        missing = list(range(len(scenes))) if force_new else [i for i, scene in enumerate(scenes) if not _resolve_scene_main_image(scene)]
        if not missing:
            _update_job(job_id, "completed", 100, "✅ 모든 장면 이미지가 이미 준비되어 있습니다.", script_data=script_data)
            return

        _update_job(job_id, "generating_images", 5, f"🎨 장면 이미지 생성 시작... 병렬 처리 중 (0/{len(missing)})", script_data=script_data)
        from backend.services.image_generator import generate_scene_image
        images_dir = job_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        persistent_dir = OUTPUT_DIR / "cache" / "images" / "jobs" / job_id
        persistent_dir.mkdir(parents=True, exist_ok=True)

        # The host may have multiple Codex image workers watching output/agy_requests.
        # Dispatch several scene requests at once so the UI does not appear stuck
        # on scene 1 while the backend waits sequentially.
        max_parallel = min(3, max(len(missing), 1))
        semaphore = asyncio.Semaphore(max_parallel)
        progress_lock = asyncio.Lock()
        completed_count = 0

        async def generate_one(i: int):
            nonlocal completed_count
            scene = scenes[i]
            scene_id = scene.get("scene_id", i + 1)
            async with semaphore:
                async with progress_lock:
                    started = completed_count + 1
                    progress = 5 + int(90 * completed_count / max(len(missing), 1))
                    _update_job(
                        job_id,
                        "generating_images",
                        progress,
                        f"🎨 장면 {scene_id} 이미지 생성 요청 중... (완료 {completed_count}/{len(missing)}, 동시 {max_parallel}개)",
                        script_data=script_data,
                    )
                char_id = scene.get("character_id", "char_1")
                char_meta = char_lookup.get(char_id, {})
                enriched_scene = {
                    **scene,
                    "character_description": char_meta.get("description", "A character"),
                    "_image_batch_id": job_id if force_new else "",
                }
                generated_path = await generate_scene_image(
                    enriched_scene,
                    images_dir,
                    topic=topic_context,
                    situation=situation_context,
                    visual_style=visual_style,
                    log_callback=lambda m: _update_job(
                        job_id,
                        "generating_images",
                        5 + int(90 * completed_count / max(len(missing), 1)),
                        m,
                        script_data=script_data,
                    ),
                )
                persistent_path = persistent_dir / f"scene_{scene_id}.png"
                shutil.copy2(generated_path, persistent_path)
                rel = _output_relative_path(persistent_path)
                if not rel:
                    raise RuntimeError("generated image path is outside output directory")
                scene["image_path"] = rel
                scene["generated_image_path"] = rel
                scene["overlays"] = [{"type": "image", "content": rel, "position": "blackboard", "startTime": 0, "duration": 5}]
                async with progress_lock:
                    completed_count += 1
                    _update_job(
                        job_id,
                        "generating_images",
                        5 + int(90 * completed_count / max(len(missing), 1)),
                        f"✅ 장면 {scene_id} 이미지 저장 완료 ({completed_count}/{len(missing)})",
                        script_data=script_data,
                    )

        await asyncio.gather(*(generate_one(i) for i in missing))

        script_data["image_job_id"] = job_id
        script_data["images_ready_for_final"] = True
        _update_job(job_id, "completed", 100, "✅ 전체 장면 이미지 준비 완료!", script_data=script_data)
    except Exception as e:
        logger.error(f"[{job_id}] Scene image generation failed: {e}", exc_info=True)
        _update_job(job_id, "error", 0, f"❌ 장면 이미지 생성 실패: {e}", script_data=script_data)


@router.post("/generate-scene-images")
async def start_scene_images_generation(req: SceneImagesGenerateRequest, background_tasks: BackgroundTasks, current_user: str = Depends(get_current_user)):
    """Start missing scene image generation as a background job."""
    job_id = str(uuid.uuid4())[:8]
    job_dir = TEMP_DIR / job_id
    job_dir.mkdir(exist_ok=True)
    if req.force_new:
        _clear_scene_generated_images(req.script_data)

    jobs[job_id] = {
        "status": "generating_images",
        "job_type": "images",
        "progress": 1,
        "message": "🎨 새 이미지 생성 작업 시작..." if req.force_new else "🎨 장면 이미지 생성 작업 시작...",
        "video_url": None,
        "script_data": req.script_data,
        "logs": ["🎨 새 이미지 생성 작업 시작..." if req.force_new else "🎨 장면 이미지 생성 작업 시작..."],
    }
    logger.info(f"[{job_id}] Scene image generation job queued. force_new={req.force_new}")
    background_tasks.add_task(run_scene_images_pipeline, job_id, req.script_data, job_dir, req.force_new)
    return {"job_id": job_id, "status": "generating_images", "job_type": "images"}


@router.get("/active-video-job")
async def get_active_video_job(current_user: str = Depends(get_current_user)):
    """Return the active final-video job so a refreshed browser can reconnect."""
    active_job = _find_active_video_job()
    if not active_job:
        return {"active": False}
    return {
        "active": True,
        "job_id": active_job.get("job_id"),
        "status": active_job.get("status"),
        "progress": active_job.get("progress", 0),
        "message": active_job.get("message", ""),
        "video_url": active_job.get("video_url"),
        "history_id": active_job.get("history_id"),
    }


@router.post("/generate-video")
async def start_video_generation(req: VideoGenerateRequest, background_tasks: BackgroundTasks, current_user: str = Depends(get_current_user)):
    """Start video generation using provided script and assets."""
    scenes = (req.script_data or {}).get("scenes", []) or []
    missing_image_scene_ids = []
    for idx, scene in enumerate(scenes):
        if not _resolve_scene_main_image(scene):
            missing_image_scene_ids.append(scene.get("scene_id", idx + 1))
    if missing_image_scene_ids:
        return {
            "error": "장면 이미지가 아직 없습니다. 먼저 '전체 장면 이미지 생성'을 완료한 뒤 최종 영상을 생성해주세요.",
            "missing_images": missing_image_scene_ids,
        }

    allowed, active_job = _can_start_video_job()
    if not allowed:
        return {
            "error": "이미 다른 영상 생성이 진행 중입니다. 완료 후 새 영상을 생성해주세요.",
            "active_job": active_job,
        }

    job_id = str(uuid.uuid4())[:8]
    job_dir = TEMP_DIR / job_id
    job_dir.mkdir(exist_ok=True)

    jobs[job_id] = {
        "status": "pending",
        "job_type": "video",
        "progress": 5,
        "message": "🎬 영상 생성 시작... 브라우저를 닫아도 서버에서 계속 생성됩니다.",
        "video_url": None,
        "script_data": req.script_data,
        "logs": ["🎬 영상 생성 시작... 브라우저를 닫아도 서버에서 계속 생성됩니다."],
    }

    logger.info(f"[{job_id}] Video Job created from script.")
    # Pipeline runs first; cleanup is a non-blocking fire-and-forget after the response.
    background_tasks.add_task(run_video_pipeline, job_id, req.script_data, job_dir)
    background_tasks.add_task(_cleanup_old_files_safe)

    return {"job_id": job_id, "status": "pending"}


@router.post("/upload-youtube")
async def upload_to_youtube(req: YouTubeUploadRequest, current_user: str = Depends(get_current_user)):
    """Upload the generated video to YouTube."""
    job_id = req.job_id
    video_path = OUTPUT_DIR / f"shorts_{job_id}.mp4"
    
    if not video_path.exists():
        return {"error": "비디오 파일을 찾을 수 없습니다. 먼저 영상을 생성해주세요."}
        
    try:
        logger.info(f"[{job_id}] YouTube Upload Start: '{req.title}'")
        # Run in a thread-safe way as it might involve blocking OAuth flow locally
        video_id = await asyncio.to_thread(
            upload_video,
            str(video_path),
            req.title,
            req.description,
            req.tags
        )
        
        if video_id:
            return {"status": "success", "video_id": video_id}
        else:
            return {"error": "유튜브 업로드에 실패했습니다."}
    except Exception as e:
        logger.error(f"[{job_id}] YouTube Upload Failed: {str(e)}")
        return {"error": str(e)}


@router.get("/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str):
    """Get the current status of a generation job."""
    if job_id not in jobs:
        video_path = OUTPUT_DIR / f"shorts_{job_id}.mp4"
        history_match = next(
            (item for item in list_history_entries() if item.get("job_id") == job_id),
            None,
        )
        if video_path.exists() and history_match:
            return JobStatus(
                job_id=job_id,
                status="completed",
                progress=100,
                message="✅ 모든 작업 완성!",
                logs=["✅ 서버 재시작 후 완료된 영상 상태를 복구했습니다."],
                video_url=f"/output/shorts_{job_id}.mp4",
                script_data=history_match.get("script_data"),
                history_id=history_match.get("id"),
            )
        return JobStatus(
            job_id=job_id,
            status="not_found",
            progress=0,
            message="작업을 찾을 수 없습니다.",
            logs=[]
        )

    job = jobs[job_id]
    return JobStatus(job_id=job_id, **job)


@router.get("/history", response_model=list[HistoryItem])
async def get_history(current_user: str = Depends(get_current_user)):
    return [HistoryItem(**item) for item in list_history_entries()]


@router.get("/history/{entry_id}", response_model=HistoryItem)
async def get_history_detail(entry_id: str, current_user: str = Depends(get_current_user)):
    item = get_history_entry(entry_id)
    if not item:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다.")

    return HistoryItem(**item)


@router.delete("/history/{entry_id}")
async def delete_history(entry_id: str, current_user: str = Depends(get_current_user)):
    return _delete_history_item(entry_id)


@router.post("/history/{entry_id}/delete")
async def delete_history_fallback(entry_id: str, current_user: str = Depends(get_current_user)):
    return _delete_history_item(entry_id)


def _delete_history_item(entry_id: str):
    item = delete_history_entry(entry_id)
    if not item:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다.")

    video_url = item.get("video_url", "")
    if video_url.startswith("/output/"):
        filename = Path(video_url).name
    else:
        filename = f"shorts_{item.get('job_id', '')}.mp4"

    if filename:
        video_path = OUTPUT_DIR / filename
        try:
            if video_path.exists() and video_path.is_file():
                video_path.unlink()
        except Exception as e:
            logger.warning(f"Could not delete history video file {video_path}: {e}")

    return {"status": "deleted", "id": entry_id}


@router.get("/download/{filename}")
async def download_file(filename: str):
    """Serve a file as an attachment for forcing downloads (fixes mobile download issues)."""
    file_path = OUTPUT_DIR / filename
    
    if not file_path.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    
    # We use FileResponse with filename argument to trigger 'Content-Disposition: attachment'
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="video/mp4"
    )


def clean_zombie_rendering_processes():
    """Scan /proc inside the container for stale chrome, remotion, ffmpeg, or node processes older than 1 hour and kill them."""
    import os
    import signal
    import time
    
    logger.info("🧹 Starting proactive cleanup of zombie rendering processes inside the container...")
    try:
        now = time.time()
        killed_count = 0
        for pid_str in os.listdir('/proc'):
            if pid_str.isdigit():
                pid = int(pid_str)
                if pid == 1:
                    continue
                try:
                    stat_info = os.stat(f'/proc/{pid}')
                    age_seconds = now - stat_info.st_mtime
                    if age_seconds > 3600:  # Older than 1 hour
                        try:
                            with open(f'/proc/{pid}/cmdline', 'r') as f:
                                cmdline = f.read()
                        except FileNotFoundError:
                            continue
                        
                        if any(x in cmdline for x in ['chrome', 'remotion', 'ffmpeg', 'node']):
                            logger.info(f"🧹 Found and killing zombie process: PID {pid} (Age: {age_seconds/3600:.2f} hours) | Cmd: {cmdline[:150]}")
                            os.kill(pid, signal.SIGKILL)
                            killed_count += 1
                except Exception:
                    pass
        if killed_count > 0:
            logger.info(f"🧹 Cleanup complete. Total zombie processes killed: {killed_count}")
        else:
            logger.info("🧹 No zombie processes found.")
    except Exception as e:
        logger.error(f"🧹 Error during zombie process cleanup: {e}")


async def run_video_pipeline(job_id: str, script_data: dict, job_dir: Path):
    """Run the asset generation and video composition steps."""
    # Proactively clean up zombie rendering processes inside the container
    clean_zombie_rendering_processes()
    
    try:
        sanitize_scene_scripts(script_data)
        apply_visual_continuity_context(
            script_data,
            topic=script_data.get("topic", "") or script_data.get("subject", ""),
            direction=(script_data.get("situation_setting") or {}).get("situation", ""),
        )
        await enrich_script_metadata(
            script_data,
            topic=script_data.get("topic", "") or script_data.get("subject", ""),
            situation=(script_data.get("situation_setting") or {}).get("situation", ""),
        )

        scenes = script_data["scenes"]
        duration_target = script_data.get("duration_target") or {}
        characters_list = script_data.get("characters", [])
        # Create a lookup for character details
        char_lookup = {c["id"]: c for c in characters_list}
        num_scenes = len(scenes)
        visual_style = script_data.get("visual_style", "south-park-comic")

        # Step 2: Resolve or generate scene images.
        # If the editor already has a selected image for a scene (manual upload or
        # per-scene AI image overlay), use it as the main visual. Do not regenerate
        # images just because the user clicked the final video button.
        logger.info(f"[{job_id}] Step 2/4: Resolving scene images... style={visual_style}")
        _update_job(job_id, "generating_images", 10, "🎨 장면 이미지 확인 중...")

        image_paths: list[Optional[str]] = [None for _ in scenes]
        missing_scene_indexes: list[int] = []
        for i, scene in enumerate(scenes):
            selected_image = _resolve_scene_main_image(scene)
            if selected_image:
                image_paths[i] = selected_image
                scene["_main_image_from_overlay"] = True
                scene["_main_image_source"] = selected_image
                rel_selected = _output_relative_path(Path(selected_image))
                if rel_selected:
                    scene["image_path"] = rel_selected
            else:
                missing_scene_indexes.append(i)

        if missing_scene_indexes:
            logger.info(
                f"[{job_id}] Reusing {num_scenes - len(missing_scene_indexes)}/{num_scenes} selected images; "
                f"generating {len(missing_scene_indexes)} missing images."
            )
            _update_job(
                job_id,
                "generating_images",
                10,
                f"🎨 선택 이미지 {num_scenes - len(missing_scene_indexes)}개 재사용, 부족한 {len(missing_scene_indexes)}개 생성 중...",
            )

            # Extract topic and situation for image context
            video_title_meta = script_data.get("video_title", {})
            if isinstance(video_title_meta, dict):
                topic_context = f"{video_title_meta.get('highlight', '')} {video_title_meta.get('rest', '')}".strip()
            else:
                topic_context = str(video_title_meta)

            situation_context = (script_data.get("situation_setting") or {}).get("situation", "")

            from backend.services.image_generator import generate_scene_image
            images_dir = job_dir / "images"
            images_dir.mkdir(exist_ok=True)

            async def generate_one_image(i: int, scene: dict) -> tuple[int, str]:
                progress = 10 + int(30 * i / num_scenes)
                msg = f"🎨 배경 이미지 생성 중... ({i+1}/{num_scenes})"
                _update_job(job_id, "generating_images", progress, msg)
                char_id = scene.get("character_id", "char_1")
                char_meta = char_lookup.get(char_id, {})
                enriched_scene = {
                    **scene,
                    "character_description": char_meta.get("description", "A character"),
                }
                generated = await generate_scene_image(
                    enriched_scene,
                    images_dir,
                    topic=topic_context,
                    situation=situation_context,
                    visual_style=visual_style,
                    log_callback=lambda m, p=progress: _update_job(job_id, "generating_images", p, m),
                )
                return i, generated

            generated_results = await asyncio.gather(*[
                generate_one_image(i, scenes[i]) for i in missing_scene_indexes
            ])
            for i, generated_path in generated_results:
                image_paths[i] = generated_path
                scene_id = scenes[i].get("scene_id", i + 1)
                persistent_dir = OUTPUT_DIR / "cache" / "images" / "jobs" / job_id
                persistent_dir.mkdir(parents=True, exist_ok=True)
                persistent_path = persistent_dir / f"scene_{scene_id}.png"
                shutil.copy2(generated_path, persistent_path)
                rel_generated = _output_relative_path(persistent_path)
                if rel_generated:
                    scenes[i]["image_path"] = rel_generated
                    scenes[i]["generated_image_path"] = rel_generated
                    scenes[i]["_main_image_source"] = str(persistent_path)
                _update_job(
                    job_id,
                    "generating_images",
                    40,
                    f"🎨 장면 {scene_id} 이미지 저장 완료 — 재시도 시 재사용됩니다.",
                )
        else:
            logger.info(f"[{job_id}] Reusing all {num_scenes} selected scene images; skipping image generation.")
            _update_job(job_id, "generating_images", 40, f"🎨 선택한 이미지 {num_scenes}개 재사용 완료! 새 이미지 생성 없음.")

        resolved_image_paths: list[str] = [str(p) for p in image_paths if p]
        if len(resolved_image_paths) != num_scenes:
            raise Exception("장면 이미지 경로를 모두 확보하지 못했습니다.")

        _update_job(job_id, "generating_images", 40, f"🎨 장면 이미지 {num_scenes}개 준비 완료!")

        # Step 3: Generate Narrations
        logger.info(f"[{job_id}] Step 3/4: Generating narrations...")
        
        full_audio_path = script_data.get("full_audio_path")
        narration_infos = []
        
        if full_audio_path:
            logger.info(f"[{job_id}] Full audio provided: {full_audio_path}. Skipping individual TTS generation.")
            _update_job(job_id, "generating_narration", 45, "🎙️ 전체 음성 파일 처리 중...")
            
            # Measure actual duration
            full_audio_abs = OUTPUT_DIR / full_audio_path
            if not full_audio_abs.exists():
                raise Exception(f"전체 음성 파일을 찾을 수 없습니다: {full_audio_path}")
                
            total_actual_duration = get_audio_duration(str(full_audio_abs))
            _update_job(job_id, "generating_narration", 50, f"🎙️ 오디오 길이 측정 완료: {total_actual_duration:.2f}초")
            
            # Predict total duration from AI
            total_predicted_duration = sum(s.get("duration", 5.0) for s in scenes)
            if total_predicted_duration == 0: total_predicted_duration = 1.0 # Safety
            
            scaling_factor = total_actual_duration / total_predicted_duration
            msg = f"🎙️ 장면별 타이밍 조정 중... (배율: {scaling_factor:.2f})"
            _update_job(job_id, "generating_narration", 55, msg)
            logger.info(f"[{job_id}] {msg}")
            
            # Rescale each scene's duration
            for scene in scenes:
                scaled_duration = scene.get("duration", 5.0) * scaling_factor
                scene["audio_duration"] = scaled_duration
                scene["duration"] = scaled_duration
            
            # Create dummy narration infos for compose_video compatibility
            for i in range(num_scenes):
                narration_infos.append({"path": "", "duration": 0})
            
            _update_job(job_id, "generating_narration", 65, "🎙️ 음성 동기화 완료!")
        else:
            _update_job(job_id, "generating_narration", 40, f"🎙️ 나레이션 생성 중... (0/{num_scenes})")
            
            # Per-scene generation with batch normalization
            narration_infos = await generate_all_narrations(
                script_data, 
                job_dir,
                progress_callback=lambda p, m: _update_job(job_id, "generating_narration", 40 + int(p * 30), m)
            )
            
            # Sync scene durations with generated audio
            for i, result in enumerate(narration_infos):
                scene = scenes[i]
                # Store actual audio duration for subtitles
                scene["audio_duration"] = result["duration"]

        total_scene_duration = _apply_scene_duration_cap(scenes, duration_target, pause_seconds=0.4)
        duration_cap = min(float(duration_target.get("max_seconds", 60.0)), 60.0)
        msg = f"⏱️ 최종 영상 길이 예산 적용: {total_scene_duration:.2f}초 / 최대 {duration_cap:.2f}초"
        _update_job(job_id, "generating_narration", 68, msg)
        logger.info(f"[{job_id}] {msg}")

        _update_job(job_id, "generating_narration", 70, f"🎙️ 나레이션 {num_scenes}개 완성!")

        scene_video_paths = [None for _ in scenes]

        # Step 4: Composing Video (Remotion)
        logger.info(f"[{job_id}] Step 4/4: Composing video...")
        _update_job(job_id, "composing_video", 75, "🎬 영상 조립 및 자막 생성 중...")
        
        # Get durations for subtitles (synchronized with scene pauses)
        durations = [s["duration"] for s in scenes]
        generate_subtitles(scenes, durations, job_dir)

        # Pass _update_job to compose_video for granular progress reporting
        video_path = await compose_video(
            scenes, resolved_image_paths, narration_infos, job_dir, job_id,
            scenes_metadata=script_data,
            scene_videos=scene_video_paths,
            progress_callback=lambda p, m: _update_job(job_id, "composing_video", 80 + int(p * 19), m)
        )

        logger.info(f"[{job_id}] ✅ Video completed: {video_path}")
        video_url = f"/output/shorts_{job_id}.mp4"
        history_entry = save_history_entry(
            build_history_entry(job_id=job_id, script_data=script_data, video_url=video_url)
        )
        _update_job(
            job_id, "completed", 100, "✅ 모든 작업 완성!",
            video_url=video_url,
            history_id=history_entry["id"],
        )

    except Exception as e:
        logger.error(f"[{job_id}] ❌ Error: {str(e)}", exc_info=True)
        _update_job(job_id, "error", 0, f"❌ 오류 발생: {str(e)}")


def _update_job(job_id: str, status: str, progress: int, message: str, **kwargs):
    """Update job status and append to log history."""
    if job_id in jobs:
        job = jobs[job_id]
        job.update({
            "status": status,
            "progress": progress,
            "message": message,
            **kwargs,
        })
        
        # Maintain a history of logs for this job
        if "logs" not in job:
            job["logs"] = []
        
        # Avoid duplicate consecutive logs if same message
        if not job["logs"] or job["logs"][-1] != message:
            job["logs"].append(message)
            
        logger.info(f"[{job_id}] Status: {status} | {progress}% | {message}")


# --- Legacy Support (optional, for backward compatibility) ---
@router.post("/generate")
async def legacy_start_generation(req: GenerateRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())[:8]
    job_dir = TEMP_DIR / job_id
    job_dir.mkdir(exist_ok=True)
    jobs[job_id] = {"status": "pending", "job_type": "video", "progress": 5, "message": "🚀 생성 시작..."}
    
    async def legacy_pipeline():
        try:
            script_data = await generate_script(req.topic, req.tags, req.direction, req.style)
            await run_video_pipeline(job_id, script_data, job_dir)
        except Exception as e:
            _update_job(job_id, "error", 0, str(e))
            
    background_tasks.add_task(legacy_pipeline)
    return {"job_id": job_id, "status": "pending"}
