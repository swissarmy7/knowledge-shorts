"""
Video Composer Service
Uses Remotion to compose final video with animations.
Falls back to FFmpeg if Remotion is not available.
"""
import json
import shutil
import subprocess
from pathlib import Path
from backend.config import OUTPUT_DIR, VIDEO_WIDTH, VIDEO_HEIGHT, BASE_DIR, REMOTION_CODEC, REMOTION_CONCURRENCY

# Remotion project directory
VIDEO_ENGINE_DIR = BASE_DIR / "video-engine"

# BGM file
BGM_PATH = BASE_DIR / "Sakura_Serenade.mp3"


async def compose_video(
    scenes: list[dict],
    images: list[str],
    narrations: list[dict],
    job_dir: Path,
    job_id: str,
    scenes_metadata: dict = None,
) -> str:
    """Compose final video using Remotion."""

    # Prepare Remotion public directory with assets
    public_dir = VIDEO_ENGINE_DIR / "public"
    images_dir = public_dir / "images"
    audio_dir = public_dir / "audio"
    uploads_dir = public_dir / "uploads"
    images_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    # Copy BGM to public folder
    bgm_path_rel = None
    if BGM_PATH.exists():
        bgm_dst = public_dir / "bgm.mp3"
        shutil.copy2(str(BGM_PATH), str(bgm_dst))
        bgm_path_rel = "bgm.mp3"

    # Copy Full Narration if exists
    full_narration_rel = None
    if scenes_metadata and scenes_metadata.get("full_audio_path"):
        src_full = OUTPUT_DIR / scenes_metadata["full_audio_path"]
        if src_full.exists():
            dst_full = public_dir / "full_narration.mp3"
            shutil.copy2(str(src_full), str(dst_full))
            full_narration_rel = "full_narration.mp3"

    # Copy images and audio to Remotion public folder
    scene_data_list = []
    for i, (scene, image_path, narration) in enumerate(
        zip(scenes, images, narrations)
    ):
        scene_id = scene.get("scene_id", i + 1)

        # Copy image
        src_img = Path(image_path)
        dst_img = images_dir / f"scene_{scene_id}.png"
        shutil.copy2(str(src_img), str(dst_img))

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
        "bgmPath": bgm_path_rel,
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
        print(f"  🖼️ Scene {sd['sceneId']}: image={img_path.exists()}, audio={aud_path.exists()}")
        for ov in sd.get("overlays", []):
            if ov.get("type") == "image":
                ov_path = public_dir / ov["content"]
                print(f"    📷 Upload: {ov['content']} (exists: {ov_path.exists()})")
    if bgm_path_rel:
        bgm_check = public_dir / bgm_path_rel
        print(f"  🎵 BGM: {bgm_check} (exists: {bgm_check.exists()})")

    # Render with Remotion CLI
    try:
        # Use relative path for --props since CWD is VIDEO_ENGINE_DIR
        props_rel = scene_data_path.relative_to(VIDEO_ENGINE_DIR)

        result = subprocess.run(
            [
                "npx", "remotion", "render",
                "ShortsVideo",
                str(output_path),
                "--codec", REMOTION_CODEC,
                "--gl", "angle",
                "--props", str(props_rel),
                
                "--log=verbose",
            ],
            cwd=str(VIDEO_ENGINE_DIR),
            capture_output=True,
            timeout=300,  # 5 min timeout
            shell=True,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode != 0:
            print(f"❌ Remotion render failed with exit code {result.returncode}")
            # Print last 2000 chars of output to avoid flooding logs
            stdout_tail = (result.stdout or "")[-2000:]
            stderr_tail = (result.stderr or "")[-2000:]
            print(f"Stdout (tail): {stdout_tail}")
            print(f"Stderr (tail): {stderr_tail}")
            # Fall back to FFmpeg
            return await _compose_with_ffmpeg(
                scenes, images, narrations, job_dir, job_id
            )

        print(f"✅ [Remotion] Render successful: {output_path}")
        return str(output_path)

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"❌ Remotion failed ({e}), falling back to FFmpeg")
        return await _compose_with_ffmpeg(
            scenes, images, narrations, job_dir, job_id
        )
    except Exception as e:
        print(f"❌ Unexpected error during Remotion render: {type(e).__name__}: {e}")
        return await _compose_with_ffmpeg(
            scenes, images, narrations, job_dir, job_id
        )
    finally:
        # Clean up public assets 
        _cleanup_public(images_dir, audio_dir)


def _cleanup_public(images_dir: Path, audio_dir: Path):
    """Clean up copied assets from Remotion public dir."""
    try:
        for f in images_dir.glob("scene_*.png"):
            f.unlink()
        for f in audio_dir.glob("narration_*.mp3"):
            f.unlink()
        full_n = audio_dir.parent / "full_narration.mp3"
        if full_n.exists():
            full_n.unlink()
        bgm = images_dir.parent / "bgm.mp3"
        if bgm.exists():
            bgm.unlink()
        
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

    # Mix BGM at low volume if available
    if BGM_PATH.exists():
        input_args.extend(["-stream_loop", "-1", "-i", str(BGM_PATH)])
        bgm_idx = n * 2
        filter_complex += f";[{bgm_idx}:a]volume=0.05[bgm];[outa][bgm]amix=inputs=2:duration=first[finala]"
        map_audio = "[finala]"
    else:
        map_audio = "[outa]"

    cmd = [
        "ffmpeg", "-y",
        *input_args,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", map_audio,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

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

    return str(output_path)
