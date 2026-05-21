"""
API Routes for the Shorts Generator
"""
import uuid
import asyncio
import logging
import shutil
import time
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from backend.config import TEMP_DIR, OUTPUT_DIR, UPLOADS_DIR
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
)
from backend.services.image_generator import (
    IMAGEN_MODEL,
    build_structured_scene_prompt,
    generate_all_images,
    get_imagen_client,
    sanitize_visual_text,
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


class GenerateRequest(BaseModel):
    topic: str
    tags: list[str] = []
    direction: str = ""
    style: str = "star-instructor"  # Only Star Instructor now
    scene_count: int = 12  # 8, 10, or 12
    visual_style: str = "cute-2d"


class VideoGenerateRequest(BaseModel):
    script_data: dict


class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: int
    message: str = ""
    logs: list[str] = []
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


@router.post("/generate-script")
async def start_script_generation(req: GenerateRequest, current_user: str = Depends(get_current_user)):
    """Generate script only (Step 1 of the new interactive pipeline)."""
    job_id = str(uuid.uuid4())[:8]
    
    logger.info(f"[{job_id}] Script Generation Start: topic='{req.topic}', visual_style='{req.visual_style}'")
    
    try:
        script_data = await generate_script(req.topic, req.tags, req.direction, req.style, req.scene_count, req.visual_style)
        return {
            "job_id": job_id,
            "status": "script_ready",
            "script_data": script_data
        }
    except Exception as e:
        logger.error(f"[{job_id}] Script Generation Failed: {str(e)}")
        return {"error": str(e)}


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
    visual_style: str = "cute-2d"


@router.post("/generate-image")
async def generate_overlay_image(req: OverlayImageRequest, current_user: str = Depends(get_current_user)):
    """Generate an AI illustration image for use as an overlay."""
    from google.genai import types

    # Sync style requirements with the main image generator (2D Vector Animation / Botero)
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

    # Generate a deterministic hash for the prompt to use as a cache key
    import hashlib
    prompt_hash = hashlib.md5(f"star_instructor_v3|{req.visual_style}|{illustration_prompt}".encode()).hexdigest()
    
    # Global image cache directory
    from backend.services.image_generator import CACHE_DIR
    cached_path = CACHE_DIR / f"overlay_{prompt_hash}.png" # Using png to match main cache

    # Check cache first
    if cached_path.exists():
        logger.info(f"[AI Image] Cache hit for overlay: {cached_path.name}")
        unique_filename = f"cached_{uuid.uuid4().hex}.png"
        file_path = UPLOADS_DIR / unique_filename
        shutil.copy(cached_path, file_path)
        return {"path": f"uploads/{unique_filename}"}

    max_retries = 5
    retry_delay = 2.0
    
    for attempt in range(max_retries):
        try:
            logger.info(f"[AI Image] Generating overlay (Attempt {attempt+1}/{max_retries})...")
            response = await asyncio.to_thread(
                get_imagen_client().models.generate_images,
                model=IMAGEN_MODEL,
                prompt=illustration_prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="1:1",
                ),
            )

            # Save to uploads
            unique_filename = f"{uuid.uuid4().hex}.png"
            file_path = UPLOADS_DIR / unique_filename

            if response.generated_images:
                image_data = response.generated_images[0].image
                image_data.save(str(file_path))
                
                # Save to cache
                try:
                    shutil.copy(file_path, cached_path)
                    logger.info(f"[AI Image] Saved overlay to cache: {cached_path.name}")
                except Exception as e:
                    logger.warning(f"[AI Image] Failed to cache overlay: {e}")

                logger.info(f"[AI Image] Generated overlay image: {file_path}")
                return {"path": f"uploads/{unique_filename}"}

            logger.warning(f"[AI Image] AI generated empty result (Attempt {attempt + 1}/{max_retries}).")
            if hasattr(response, 'candidates') and response.candidates:
                for c in response.candidates:
                    logger.warning(f"[AI Image] candidate: finish_reason={c.finish_reason}")
            
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                return {"error": "이미지 생성에 실패했습니다. (AI 응답 없음) 다시 시도해주세요."}

        except Exception as e:
            error_msg = str(e)
            logger.warning(f"[AI Image] Generation attempt {attempt + 1} failed: {error_msg}")
            
            if attempt < max_retries - 1:
                import re
                wait_time = retry_delay
                if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
                    match = re.search(r"retryDelay':\s*'(\d+)s'", error_msg)
                    if match:
                        wait_time = int(match.group(1)) + 1
                    else:
                        wait_time = max(wait_time, 15.0)
                
                logger.info(f"[AI Image] Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
                retry_delay *= 2
            else:
                logger.error(f"[AI Image] All {max_retries} attempts failed.")
                return {"error": f"이미지 생성 오류: {error_msg}"}


@router.post("/generate-video")
async def start_video_generation(req: VideoGenerateRequest, background_tasks: BackgroundTasks, current_user: str = Depends(get_current_user)):
    """Start video generation using provided script and assets."""
    job_id = str(uuid.uuid4())[:8]
    job_dir = TEMP_DIR / job_id
    job_dir.mkdir(exist_ok=True)

    jobs[job_id] = {
        "status": "pending",
        "progress": 5,
        "message": "🎬 영상 생성 시작...",
        "video_url": None,
        "script_data": req.script_data,
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


async def run_video_pipeline(job_id: str, script_data: dict, job_dir: Path):
    """Run the asset generation and video composition steps."""
    try:
        sanitize_scene_scripts(script_data)
        await enrich_script_metadata(
            script_data,
            topic=script_data.get("topic", "") or script_data.get("subject", ""),
            situation=script_data.get("situation_setting", {}).get("situation", ""),
        )

        scenes = script_data["scenes"]
        characters_list = script_data.get("characters", [])
        # Create a lookup for character details
        char_lookup = {c["id"]: c for c in characters_list}
        num_scenes = len(scenes)
        visual_style = script_data.get("visual_style", "cute-2d")

        # Step 2: Generate Images
        logger.info(f"[{job_id}] Step 2/4: Generating images... style={visual_style}")
        _update_job(job_id, "generating_images", 10, "🎨 배경 이미지 생성 시작...")
        
        # Extract topic and situation for image context
        video_title_meta = script_data.get("video_title", {})
        if isinstance(video_title_meta, dict):
            topic_context = f"{video_title_meta.get('highlight', '')} {video_title_meta.get('rest', '')}".strip()
        else:
            topic_context = str(video_title_meta)
            
        situation_context = script_data.get("situation_setting", {}).get("situation", "")

        image_paths = []
        for i, scene in enumerate(scenes):
            # 10% to 40%
            progress = 10 + int(30 * i / num_scenes)
            msg = f"🎨 배경 이미지 생성 중... ({i+1}/{num_scenes})"
            _update_job(job_id, "generating_images", progress, msg)
            
            # Enrich scene with character details
            char_id = scene.get("character_id", "char_1")
            char_meta = char_lookup.get(char_id, {})
            enriched_scene = {
                **scene,
                "character_description": char_meta.get("description", "A character"),
            }

            from backend.services.image_generator import generate_scene_image
            images_dir = job_dir / "images"
            images_dir.mkdir(exist_ok=True)
            path = await generate_scene_image(
                enriched_scene, images_dir, 
                topic=topic_context, 
                situation=situation_context,
                visual_style=visual_style,
                log_callback=lambda m: _update_job(job_id, "generating_images", progress, m)
            )
            image_paths.append(path)

        _update_job(job_id, "generating_images", 40, f"🎨 이미지 {num_scenes}개 완성!")

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
                scene["duration"] = scene.get("duration", 5.0) * scaling_factor
            
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
                # Add a natural pause (0.4s buffer) after each scene dialogue for the scene duration
                scene["duration"] = result["duration"] + 0.4

        _update_job(job_id, "generating_narration", 70, f"🎙️ 나레이션 {num_scenes}개 완성!")

        # Step 4: Composing Video (Remotion)
        logger.info(f"[{job_id}] Step 4/4: Composing video...")
        _update_job(job_id, "composing_video", 75, "🎬 영상 조립 및 자막 생성 중...")
        
        # Get durations for subtitles (synchronized with scene pauses)
        durations = [s["duration"] for s in scenes]
        generate_subtitles(scenes, durations, job_dir)

        # Pass _update_job to compose_video for granular progress reporting
        video_path = await compose_video(
            scenes, image_paths, narration_infos, job_dir, job_id,
            scenes_metadata=script_data,
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
    jobs[job_id] = {"status": "pending", "progress": 5, "message": "🚀 생성 시작..."}
    
    async def legacy_pipeline():
        try:
            script_data = await generate_script(req.topic, req.tags, req.direction, req.style)
            await run_video_pipeline(job_id, script_data, job_dir)
        except Exception as e:
            _update_job(job_id, "error", 0, str(e))
            
    background_tasks.add_task(legacy_pipeline)
    return {"job_id": job_id, "status": "pending"}
