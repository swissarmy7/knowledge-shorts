"""
Video Composer Service
Uses Remotion to compose final video with animations.
Falls back to FFmpeg if Remotion is not available.
"""
import os
import re
import json
import shutil
import signal
import asyncio
import subprocess
import time
from contextlib import suppress
from pathlib import Path
from typing import Optional
from backend.config import (
    OUTPUT_DIR,
    TARGET_DURATION,
    VIDEO_WIDTH,
    VIDEO_HEIGHT,
    BASE_DIR,
    REMOTION_CODEC,
    REMOTION_CONCURRENCY,
    REMOTION_GL,
    REMOTION_BROWSER_EXECUTABLE,
    REMOTION_CHROME_MODE,
    REMOTION_RENDER_TIMEOUT,
    REMOTION_RENDER_STALL_TIMEOUT,
)

# Remotion project directory
VIDEO_ENGINE_DIR = BASE_DIR / "video-engine"


def _resolve_remotion_browser_executable() -> Optional[str]:
    """Prefer an explicitly configured browser, otherwise let Remotion manage it."""
    if REMOTION_BROWSER_EXECUTABLE:
        browser_path = Path(REMOTION_BROWSER_EXECUTABLE)
        if browser_path.exists():
            return str(browser_path)

        print(
            f"⚠️ [Remotion] Configured browser executable not found: {browser_path}. "
            "Falling back to Remotion-managed browser."
        )

    remotion_browser_candidates = [
        VIDEO_ENGINE_DIR / "node_modules" / ".remotion" / "chrome-for-testing" / "linux-arm64" / "chrome-headless-shell-linux-arm64" / "chrome-headless-shell",
        VIDEO_ENGINE_DIR / "node_modules" / ".remotion" / "chrome-for-testing" / "linux64" / "chrome-linux64" / "chrome",
        VIDEO_ENGINE_DIR / "node_modules" / ".remotion" / "chrome-headless-shell" / "linux-arm64" / "chrome-headless-shell-linux-arm64" / "headless_shell",
        VIDEO_ENGINE_DIR / "node_modules" / ".remotion" / "chrome-headless-shell" / "linux64" / "chrome-headless-shell-linux64" / "chrome-headless-shell",
    ]
    for candidate in remotion_browser_candidates:
        if candidate.exists():
            return str(candidate)

    return None


async def compose_video(
    scenes: list[dict],
    images: list[str],
    narrations: list[dict],
    job_dir: Path,
    job_id: str,
    scenes_metadata: dict = None,
    scene_videos: Optional[list[Optional[str]]] = None,
    progress_callback: callable = None,
) -> str:
    """Compose final video using Remotion."""
    if progress_callback:
        progress_callback(0, "🎬 영상 합성 준비 중...")

    # Prepare Remotion public directory with assets
    public_dir = VIDEO_ENGINE_DIR / "public"
    images_dir = public_dir / "images"
    audio_dir = public_dir / "audio"
    videos_dir = public_dir / "videos"
    uploads_dir = public_dir / "uploads"
    images_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    videos_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    # Start from a clean Remotion public asset set. Stale images in public/ can
    # make a fresh render reference another job's assets.
    _cleanup_public(images_dir, audio_dir, videos_dir)

    # Copy Full Narration if exists
    full_narration_rel = None
    if scenes_metadata and scenes_metadata.get("full_audio_path"):
        src_full = OUTPUT_DIR / scenes_metadata["full_audio_path"]
        if src_full.exists():
            dst_full = public_dir / "full_narration.mp3"
            shutil.copy2(str(src_full), str(dst_full))
            full_narration_rel = "full_narration.mp3"

    # Copy images and audio to Remotion public folder.
    scene_data_list = []
    scene_videos = scene_videos or [None for _ in scenes]
    for i, (scene, image_path, narration) in enumerate(
        zip(scenes, images, narrations)
    ):
        scene_id = scene.get("scene_id", i + 1)

        # Copy image
        src_img = Path(image_path)
        dst_img = images_dir / f"scene_{scene_id}.png"
        shutil.copy2(str(src_img), str(dst_img))

        # Optional legacy per-scene video clip support. Remotion's normal <Video>
        # uses the browser decoder. The Remotion-managed headless Chrome build on
        # this server does not reliably decode H.264 MP4, even when ffprobe says
        # the container is valid. Convert scene clips to VP8 WebM before handing
        # them to Remotion; if conversion fails, fall back visibly to the still
        # scene image instead of crashing the whole render at frame 0.
        video_path_rel = None
        scene_video_src = scene_videos[i] if i < len(scene_videos) else None
        if scene_video_src:
            src_video = Path(scene_video_src)
            if src_video.exists():
                dst_video = videos_dir / f"scene_{scene_id}.webm"
                if _prepare_scene_video_for_remotion(src_video, dst_video):
                    video_path_rel = f"videos/scene_{scene_id}.webm"
                else:
                    print(f"⚠️ [Remotion] Scene {scene_id}: scene video not browser-playable; using still image fallback for this scene")

        # Copy audio if not using full narration or if provided
        audio_path_rel = None
        if narration and narration.get("path"):
            src_audio = Path(narration["path"])
            if src_audio.exists():
                dst_audio = audio_dir / f"narration_{scene_id}.mp3"
                shutil.copy2(str(src_audio), str(dst_audio))
                audio_path_rel = f"audio/narration_{scene_id}.mp3"
                # Get actual audio duration
                duration = _get_audio_duration(str(src_audio))

        # Prepare overlays: handle user uploads
        processed_overlays = []
        for ov in scene.get("overlays", []):
            ov_content = ov.get("content", "")
            if scene.get("_main_image_from_overlay") and ov.get("type") == "image":
                # The selected editor image is already used as the full scene
                # visual layer. Rendering it again as an overlay would duplicate
                # the same picture on top of itself.
                continue
            if ov_content.startswith("uploads/"):
                # Copy the upload to remotion public
                src_upload = OUTPUT_DIR / ov_content
                if src_upload.exists():
                    dst_upload = public_dir / ov_content
                    dst_upload.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src_upload), str(dst_upload))
                
                processed_overlays.append({
                    **ov,
                    "type": "image",
                    "content": ov_content,
                })
            else:
                processed_overlays.append({
                    **ov,
                    "type": "text",
                })

        # Narrate with dynamic voice category
        char_id = scene.get("character_id", "char_1")
        voice_cat = next((c["voice_category"] for c in scenes_metadata.get("characters", []) if c["id"] == char_id), "adult_female")
        
        # Call orchestration for narration (this logic might be slightly different depending on how scenes are passed)
        # Assuming scenes in compose_video are the ones from script_generator
        
        # Prepare for image generation
        scene_for_image = {
            **scene,
            "character_description": next((c["description"] for c in scenes_metadata.get("characters", []) if c["id"] == char_id), ""),
            "background_description": scene.get("background_description", ""),
        }
        
        # (The actual calls to generate_narration and generate_image are usually in a higher orchestration layer,
        # but video_composer processes the final scene_data.json)

        scene_data_list.append({
            "sceneId": scene_id,
            "imagePath": f"images/scene_{scene_id}.png",
            "videoPath": video_path_rel or "",
            "audioPath": audio_path_rel or "",
            "script": scene.get("script", ""),
            "durationInSeconds": scene.get("duration", 5.0),
            "motion": scene.get("motion", "talking"),
            "characterId": char_id,
            "volume": scene.get("volume", 1.0),
            "overlays": processed_overlays,
        })

    # Write scene data JSON for Remotion
    scene_data = {
        "videoTitle": scenes_metadata.get("video_title", "AI Shorts"),
        "subject": scenes_metadata.get("subject", "지식"),
        "situationSetting": scenes_metadata.get("situation_setting", {}),
        "characters": scenes_metadata.get("characters", []),
        "scenes": scene_data_list,
        "fullNarrationPath": full_narration_rel,
    }

    scene_data_path = VIDEO_ENGINE_DIR / "src" / "scene-data.json"
    with open(scene_data_path, "w", encoding="utf-8") as f:
        json.dump(scene_data, f, ensure_ascii=False, indent=2)

    # Output path
    output_filename = f"shorts_{job_id}.mp4"
    output_path = OUTPUT_DIR / output_filename

    # --- DIAGNOSTIC: Verify all assets exist before render ---
    print(f"🎬 [Remotion] Starting render for job {job_id}")
    print(f"  📁 Scene data: {scene_data_path} (exists: {scene_data_path.exists()})")
    for sd in scene_data_list:
        img_path = public_dir / sd["imagePath"]
        aud_path = public_dir / sd["audioPath"]
        print(f"  🖼️ Scene {sd['sceneId']}: image={img_path.exists()}, video={bool(sd.get('videoPath'))}, audio={aud_path.exists()}")
        for ov in sd.get("overlays", []):
            if ov.get("type") == "image":
                ov_path = public_dir / ov["content"]
                print(f"    📷 Upload: {ov['content']} (exists: {ov_path.exists()})")
    # Render with Remotion CLI (Async for progress parsing)
    try:
        # Use relative path for --props since CWD is VIDEO_ENGINE_DIR
        props_rel = scene_data_path.relative_to(VIDEO_ENGINE_DIR)

        browser_executable = _resolve_remotion_browser_executable()

        # Construct the command string for shell execution
        browser_executable_arg = f"--browser-executable {browser_executable}" if browser_executable else ""
        
        cmd_str = (
            f"xvfb-run -a npx remotion render "
            f"ShortsVideo "
            f"{output_path} "
            f"--codec {REMOTION_CODEC} "
            f"--gl {REMOTION_GL} "
            f"--concurrency {REMOTION_CONCURRENCY} "
            f"--props {props_rel} "
            f"--headless=new "
            f"--chrome-mode {REMOTION_CHROME_MODE} "
            f"{browser_executable_arg}"
        )

        print(f"🎬 [Remotion] Executing (shell): {cmd_str}")
        if progress_callback:
            progress_callback(0.05, "🎬 렌더링 엔진 초기화 중...")

        # Inject environment variables
        render_env = os.environ.copy()
        render_env["REMOTION_HEADLESS_MODE"] = "new"
        render_env["REMOTION_CHROME_MODE"] = REMOTION_CHROME_MODE
        render_env["PUPPETEER_SKIP_CHROMIUM_DOWNLOAD"] = "true"
        if browser_executable:
            render_env["REMOTION_BROWSER_EXECUTABLE"] = browser_executable

        process = await asyncio.create_subprocess_shell(
            cmd_str,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(VIDEO_ENGINE_DIR),
            env=render_env,
            preexec_fn=os.setsid,
        )

        total_frames = 1
        current_frame = 0
        last_progress_bucket = -1
        render_started_at = time.monotonic()
        last_output_at = render_started_at
        last_frame_progress_at = render_started_at
        last_file_activity_at = render_started_at
        last_output_size = output_path.stat().st_size if output_path.exists() else 0
        temp_output_sizes: dict[str, int] = {}
        last_file_progress_notice_at = 0.0

        # Pattern to match progress in Remotion output
        frame_pattern = re.compile(r"(\d+)/(\d+)")

        async def terminate_render_process(reason: str):
            print(f"⏱️ [Remotion] Terminating stalled render for job {job_id}: {reason}")
            with suppress(ProcessLookupError):
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            try:
                await asyncio.wait_for(process.wait(), timeout=10)
            except asyncio.TimeoutError:
                with suppress(ProcessLookupError):
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                with suppress(Exception):
                    await process.wait()

        async def watchdog():
            nonlocal last_file_activity_at, last_output_size, last_file_progress_notice_at
            while process.returncode is None:
                await asyncio.sleep(5)
                now = time.monotonic()

                # Remotion often stops printing after 95% while its ffmpeg/compositor is
                # still writing. During render it may write /tmp/react-motion-render*/
                # pre-encode.mp4 first and only later move/mux to the final output path.
                # Treat both final MP4 growth and temp pre-encode growth as activity.
                watched_files = [output_path]
                watched_files.extend(Path("/tmp").glob("react-motion-render*/pre-encode.mp4"))

                for watched in watched_files:
                    if not watched.exists():
                        continue
                    current_size = watched.stat().st_size
                    key = str(watched)
                    previous_size = last_output_size if watched == output_path else temp_output_sizes.get(key, 0)
                    if current_size > previous_size:
                        if watched == output_path:
                            last_output_size = current_size
                        else:
                            temp_output_sizes[key] = current_size
                        last_file_activity_at = now
                        if progress_callback and now - last_file_progress_notice_at > 30:
                            last_file_progress_notice_at = now
                            label = "최종 MP4" if watched == output_path else "임시 MP4"
                            progress_callback(
                                0.97,
                                f"🎬 Remotion {label} 작성 중... ({current_size / (1024 * 1024):.1f}MB)",
                            )

                # Near the last frames Remotion can spend a long time finalizing even
                # without visible file growth. Give that phase a larger grace window.
                stall_timeout = REMOTION_RENDER_STALL_TIMEOUT
                if total_frames > 1 and current_frame >= max(1, total_frames - 2):
                    stall_timeout = max(stall_timeout, 900)

                if REMOTION_RENDER_TIMEOUT and now - render_started_at > REMOTION_RENDER_TIMEOUT:
                    return f"total timeout {REMOTION_RENDER_TIMEOUT:.0f}s exceeded"

                # stdout can keep trickling even when Chrome/compositor is stuck.
                # Treat only real frame advancement or MP4 growth as render
                # activity. This prevents 95% hangs where CPU spins forever while
                # pre-encode.mp4 and frame counters do not move.
                last_activity_at = max(last_frame_progress_at, last_file_activity_at)
                if stall_timeout and now - last_activity_at > stall_timeout:
                    return f"no Remotion frame progress or MP4 growth for {stall_timeout:.0f}s"
            return None

        async def stream_reader(stream, is_stderr=False):
            nonlocal total_frames, current_frame, last_progress_bucket, last_output_at, last_frame_progress_at
            while True:
                line = await stream.readline()
                if not line:
                    break
                last_output_at = time.monotonic()
                line_text = line.decode("utf-8", errors="replace").strip()
                if line_text:
                    if not is_stderr: 
                        print(f"  [Remotion] {line_text}")
                    else: 
                        print(f"  [Remotion Err] {line_text}")
                    
                    # Parse progress if callback provided
                    if progress_callback:
                        match = frame_pattern.search(line_text)
                        if match:
                            next_frame = int(match.group(1))
                            if next_frame > current_frame:
                                last_frame_progress_at = time.monotonic()
                            current_frame = next_frame
                            total_frames = int(match.group(2))
                            if total_frames > 0:
                                percent = current_frame / total_frames
                                bucket = min(100, int(percent * 100) // 5 * 5)
                                if bucket > last_progress_bucket:
                                    last_progress_bucket = bucket
                                    progress_callback(
                                        percent,
                                        f"🎬 영상 프레임 렌더링 중... {bucket}% ({current_frame}/{total_frames})",
                                    )
                        elif "Copying" in line_text or "Encoding" in line_text:
                            progress_callback(
                                current_frame / total_frames if total_frames > 0 else 0.8,
                                f"🎬 {line_text}",
                            )

        stdout_task = asyncio.create_task(stream_reader(process.stdout))
        stderr_task = asyncio.create_task(stream_reader(process.stderr, is_stderr=True))
        wait_task = asyncio.create_task(process.wait())
        watchdog_task = asyncio.create_task(watchdog())

        done, pending = await asyncio.wait(
            {wait_task, watchdog_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if watchdog_task in done:
            reason = watchdog_task.result()
            if reason:
                if progress_callback:
                    progress_callback(0.95, f"⏱️ Remotion 렌더링 마무리 정체 감지, 출력 파일 확인 중... ({reason})")
                await terminate_render_process(reason)
                await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
                # Remotion can render all frames and then hang during final cleanup.
                # If a valid MP4 was already written, keep it instead of falling back
                # to the static FFmpeg composer (which loses titles/subtitles/effects).
                if output_path.exists() and output_path.stat().st_size > 1024 and _is_valid_video(output_path):
                    print(f"✅ [Remotion] Using already-written output after watchdog: {output_path}")
                    if progress_callback:
                        progress_callback(0.98, "🎬 Remotion 출력 파일 확인 완료, YouTube 포맷 변환 중...")
                    await _reencode_for_youtube(output_path)
                    await _enforce_duration_limit(output_path, max_duration=float(TARGET_DURATION))
                    if progress_callback:
                        progress_callback(1.0, "🎬 렌더링 완료!")
                    return str(output_path)
                if output_path.exists():
                    print(f"⚠️ [Remotion] Watchdog output is not a finalized MP4 yet: {output_path} ({output_path.stat().st_size} bytes)")
                raise asyncio.TimeoutError(reason)

        watchdog_task.cancel()
        with suppress(asyncio.CancelledError):
            await watchdog_task
        return_code = await wait_task
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)

        if return_code != 0:
            message = f"Remotion render failed with exit code {return_code}"
            print(f"❌ {message}")
            return await _compose_with_ffmpeg_if_allowed(
                scenes, images, narrations, job_dir, job_id, message
            )

        print(f"✅ [Remotion] Render successful: {output_path}")
        if progress_callback:
            progress_callback(0.98, "🎬 YouTube 호환 포맷으로 변환 중...")
        await _reencode_for_youtube(output_path)
        if progress_callback:
            progress_callback(0.99, f"⏱️ 최종 길이 {TARGET_DURATION:.0f}초 제한 확인 중...")
        await _enforce_duration_limit(output_path, max_duration=float(TARGET_DURATION))
        if progress_callback:
            progress_callback(1.0, "🎬 렌더링 완료!")

        return str(output_path)

    except (asyncio.TimeoutError, FileNotFoundError) as e:
        print(f"❌ Remotion failed ({e})")
        return await _compose_with_ffmpeg_if_allowed(
            scenes, images, narrations, job_dir, job_id, str(e)
        )
    except Exception as e:
        print(f"❌ Unexpected error during Remotion render: {type(e).__name__}: {e}")
        return await _compose_with_ffmpeg_if_allowed(
            scenes, images, narrations, job_dir, job_id, f"{type(e).__name__}: {e}"
        )
    finally:
        # Clean up public assets 
        _cleanup_public(images_dir, audio_dir, videos_dir)


def _prepare_scene_video_for_remotion(src_video: Path, dst_video: Path) -> bool:
    """Convert an MP4 scene clip into a browser-playable WebM for Remotion <Video>.

    ffprobe-valid H.264 MP4 is not enough here: the bundled/headless Chrome used by
    Remotion may lack proprietary H.264 decoding. VP8 WebM is the safer input for
    browser-side video playback. Audio is stripped because narration is handled by
    Remotion separately.
    """
    try:
        dst_video.parent.mkdir(parents=True, exist_ok=True)
        tmp_video = dst_video.with_suffix(".tmp.webm")
        if tmp_video.exists():
            tmp_video.unlink()

        cmd = [
            "ffmpeg", "-y",
            "-i", str(src_video),
            "-an",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p",
            "-r", "30",
            "-c:v", "libvpx",
            "-deadline", "good",
            "-cpu-used", "5",
            "-crf", "32",
            "-b:v", "2500k",
            str(tmp_video),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode != 0 or not tmp_video.exists() or tmp_video.stat().st_size < 1024:
            print(f"⚠️ [Remotion] WebM conversion failed for {src_video}: {(result.stderr or '')[-500:]}")
            if tmp_video.exists():
                tmp_video.unlink()
            return False

        if not _is_valid_video(tmp_video):
            print(f"⚠️ [Remotion] Converted WebM is invalid for {src_video}: {tmp_video}")
            tmp_video.unlink(missing_ok=True)
            return False

        tmp_video.replace(dst_video)
        print(f"✅ [Remotion] Scene video converted for browser playback: {src_video.name} -> {dst_video.name}")
        return True
    except Exception as exc:
        print(f"⚠️ [Remotion] Scene video conversion exception for {src_video}: {type(exc).__name__}: {exc}")
        with suppress(Exception):
            tmp_video.unlink()  # type: ignore[name-defined]
        return False


def _is_valid_video(video_path: Path) -> bool:
    """Return True only when ffprobe can read a finalized MP4 container."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return False
        return float((result.stdout or "0").strip() or 0) > 0
    except Exception:
        return False


async def _reencode_for_youtube(video_path: Path) -> None:
    """Re-encode with YouTube Shorts-compatible settings.

    Remotion outputs yuvj420p (full-range) with bt470bg color space, which causes
    YouTube to misinterpret the video and apply incorrect scaling/cropping.
    This step converts to yuv420p (limited-range) + BT.709 — the standard for
    1080p web video — so YouTube renders it at the correct size without cropping.
    """
    temp_path = video_path.with_suffix(".yt.mp4")
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", "format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
        "-colorspace", "bt709",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-color_range", "tv",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        str(temp_path),
    ]
    result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True)
    if result.returncode == 0 and temp_path.exists():
        temp_path.replace(video_path)
        print(f"✅ [YouTube] Re-encoded for compatibility: {video_path.name}")
    else:
        print(f"⚠️ [YouTube] Re-encode failed (keeping original): {result.stderr[-300:]}")
        if temp_path.exists():
            temp_path.unlink()


def _build_atempo_filter(speed_factor: float) -> str:
    """Build a valid ffmpeg atempo chain for the requested factor."""
    if speed_factor <= 0:
        return "atempo=1.0"

    filters: list[str] = []
    remaining = float(speed_factor)

    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0

    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5

    filters.append(f"atempo={remaining:.6f}")
    return ",".join(filters)


async def _enforce_duration_limit(video_path: Path, max_duration: float = 60.0) -> None:
    """As a final safeguard, speed-adjust the rendered MP4 if it exceeds the limit."""
    actual_duration = _get_audio_duration(str(video_path))
    if actual_duration <= max_duration:
        return

    speed_factor = actual_duration / max_duration
    temp_path = video_path.with_suffix(".capped.mp4")
    video_filter = f"setpts=PTS/{speed_factor:.6f}"
    audio_filter = _build_atempo_filter(speed_factor)
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-filter:v", video_filter,
        "-filter:a", audio_filter,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-colorspace", "bt709",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-color_range", "tv",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        str(temp_path),
    ]
    result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True)
    if result.returncode == 0 and temp_path.exists():
        temp_path.replace(video_path)
        final_duration = _get_audio_duration(str(video_path))
        print(
            f"✅ [DurationCap] Adjusted rendered video from {actual_duration:.2f}s "
            f"to {final_duration:.2f}s using {speed_factor:.4f}x speed-up."
        )
    else:
        print(f"⚠️ [DurationCap] Failed to cap duration: {result.stderr[-300:]}")
        if temp_path.exists():
            temp_path.unlink()


def _cleanup_public(images_dir: Path, audio_dir: Path, videos_dir: Optional[Path] = None):
    """Clean up copied assets from Remotion public dir."""
    try:
        for f in images_dir.glob("scene_*.png"):
            f.unlink()
        for f in audio_dir.glob("narration_*.mp3"):
            f.unlink()
        if videos_dir and videos_dir.exists():
            for pattern in ("scene_*.mp4", "scene_*.webm"):
                for f in videos_dir.glob(pattern):
                    f.unlink()
        full_n = audio_dir.parent / "full_narration.mp3"
        if full_n.exists():
            full_n.unlink()
        # Clean up uploads in public
        uploads_dir = images_dir.parent / "uploads"
        if uploads_dir.exists():
            for f in uploads_dir.glob("*"):
                f.unlink()
    except Exception:
        pass


def _get_audio_duration(audio_path: str) -> float:
    """Get actual audio duration using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
        )
        info = json.loads(result.stdout)
        return float(info["format"]["duration"])
    except Exception:
        return 5.0


async def _compose_with_ffmpeg_if_allowed(
    scenes: list[dict],
    images: list[str],
    narrations: list[dict],
    job_dir: Path,
    job_id: str,
    reason: str,
) -> str:
    """Only use static FFmpeg fallback when explicitly enabled.

    The static fallback loses Remotion title/subtitle/effects, which is worse than
    a visible error for this app's current workflow. Keep the old fallback behind
    an escape hatch for emergency/manual operation.
    """
    if os.getenv("ALLOW_STATIC_FFMPEG_FALLBACK", "false").lower() in {"1", "true", "yes", "on"}:
        print(f"⚠️ [Fallback] ALLOW_STATIC_FFMPEG_FALLBACK enabled; using static FFmpeg fallback after: {reason}")
        return await _compose_with_ffmpeg(scenes, images, narrations, job_dir, job_id)

    raise RuntimeError(
        "Remotion 렌더링에 실패했습니다. 정적 FFmpeg fallback은 제목/자막/효과를 잃기 때문에 비활성화했습니다. "
        f"원인: {reason}"
    )


async def _compose_with_ffmpeg(
    scenes: list[dict],
    images: list[str],
    narrations: list[dict],
    job_dir: Path,
    job_id: str,
) -> str:
    """Fallback: compose video with FFmpeg (static images + audio)."""
    import subprocess

    output_filename = f"shorts_{job_id}.mp4"
    output_path = OUTPUT_DIR / output_filename

    # Build FFmpeg command for concatenating scenes
    filter_parts = []
    input_args = []

    for i, (image_path, narration) in enumerate(zip(images, narrations)):
        duration = narration.get("duration", 5.0)
        # Try to get actual duration
        actual_dur = _get_audio_duration(narration["path"])
        if actual_dur > 0:
            duration = actual_dur

        input_args.extend(["-loop", "1", "-t", str(duration), "-i", image_path])
        input_args.extend(["-i", narration["path"]])

    n = len(images)

    # Build filter complex
    filter_complex = ""
    concat_parts = ""

    for i in range(n):
        vi = i * 2
        ai = i * 2 + 1
        filter_complex += (
            f"[{vi}:v]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,"
            f"setsar=1[v{i}];"
        )
        concat_parts += f"[v{i}][{ai}:a]"

    filter_complex += f"{concat_parts}concat=n={n}:v=1:a=1[outv][outa]"

    cmd = [
        "ffmpeg", "-y",
        *input_args,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "[outa]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-colorspace", "bt709",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-color_range", "tv",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-movflags", "+faststart",
        "-shortest",
        str(output_path),
    ]

    result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        # Capture more stderr and filter out the ubiquitous version/config header
        err_output = result.stderr or ""
        # FFmpeg errors usually start after the configuration block
        if "Hyperfast Audio and Video" in err_output:
            parts = err_output.split("Hyperfast Audio and Video", 1)
            clean_err = parts[1].strip() if len(parts) > 1 else err_output
        else:
            # Fallback: take last 1000 chars which likely contain the actual error
            clean_err = err_output[-1000:].strip() if len(err_output) > 1000 else err_output
            
        raise Exception(f"FFmpeg failed: {clean_err[:800]}")

    await _enforce_duration_limit(output_path, max_duration=float(TARGET_DURATION))

    return str(output_path)
