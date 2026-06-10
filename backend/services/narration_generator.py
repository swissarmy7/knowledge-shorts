"""
Narration Generator Service
Uses Google Cloud TTS (Chirp 3.0 HD) for natural-sounding narration.
Per-scene generation with batch normalization for volume consistency.
"""
import re
import asyncio
import subprocess
import logging
from pathlib import Path
from backend.services.supertonic_local_service import generate_supertonic_local, get_voice_name

logger = logging.getLogger("shorts")

SCENE_DURATION_TARGETS = {
    8: {"min_seconds": 47.0, "max_seconds": 57.0},
    10: {"min_seconds": 46.0, "max_seconds": 56.0},
    12: {"min_seconds": 43.0, "max_seconds": 54.0},
}


def get_duration_target(scene_count: int, speed: str = "1.12") -> dict:
    return SCENE_DURATION_TARGETS.get(
        scene_count,
        {
            "min_seconds": 47.0 if scene_count < 9 else (43.0 if scene_count > 11 else 46.0),
            "max_seconds": 57.0 if scene_count < 9 else (54.0 if scene_count > 11 else 56.0),
        },
    )


def get_base_speed_factor(scenes: list[dict], scene_count: int) -> float:
    """
    Baseline speed factor for narration. Keep close to 1.0 so TTS sounds natural.
    The duration guard (Step 3) handles any real length mismatches; this only adds
    a very small constant nudge for density.
    """
    scripts = [clean_narration_text(scene.get("script", "")) for scene in scenes]
    total_chars = sum(len(script.replace(" ", "")) for script in scripts)
    avg_chars = total_chars / max(scene_count, 1)

    base_speed = 1.00

    # Keep the default close to normal speed and only nudge upward for very dense scripts.
    if avg_chars >= 48:
        base_speed += 0.03
    if avg_chars >= 62:
        base_speed += 0.03

    return min(base_speed, 1.10)


def clean_narration_text(text: str) -> str:
    """Clean text: remove action directions, punctuation that disrupts TTS, interjections."""
    clean = re.sub(r'\([^)]*\)', '', text).strip()
    clean = re.sub(r'\[[^\]]*\]', '', clean).strip()
    # Remove ellipsis (TTS reads them unnaturally)
    clean = clean.replace('...', ' ')
    # Remove commas and semicolons — Korean TTS misinterprets them as hard pauses,
    # causing unnatural mid-word breaks (e.g. "몰아냈지만," → "지만...만종교를")
    clean = re.sub(r'[,;，；]', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean if clean else text


async def generate_narration(
    text: str,
    scene_id: int,
    job_dir: Path,
    character_id: str = "char_1",
    gender: str = "female",
    role: str = "student",
    age_group: str = "young-adult",
    speed: float = 1.05,
) -> dict:
    """Generate TTS narration for a single scene using local Supertonic model with custom speed."""
    audio_dir = job_dir / "audio"
    audio_dir.mkdir(exist_ok=True)

    audio_filename = f"narration_{scene_id}.mp3"
    audio_path = audio_dir / audio_filename

    # Clean text 
    clean_text = clean_narration_text(text)

    # Select best Supertonic voice (M1~M5, F1~F5)
    voice_name = get_voice_name(character_id, gender, role, age_group)
    
    success = await generate_supertonic_local(
        text=clean_text, 
        voice_name=voice_name, 
        output_path=str(audio_path),
        speed=speed
    )
    
    if not success:
        logger.error(f"Failed to generate TTS for scene {scene_id}")
        return {"path": "", "duration": 0}

    duration = get_audio_duration(str(audio_path))
    return {"path": str(audio_path), "duration": duration}


async def generate_all_narrations(
    script_data: dict, job_dir: Path, progress_callback: callable = None
) -> list[dict]:
    """
    Generate narrations for all scenes with voice consistency.
    """
    scenes = script_data.get("scenes", [])
    num_scenes = len(scenes)
    user_speed = script_data.get("tts_settings", {}).get("speed") or "1.12"
    duration_target = script_data.get("duration_target") or get_duration_target(num_scenes, user_speed)
    
    # User manual speed override
    if user_speed:
        try:
            base_speed_factor = float(user_speed)
        except Exception:
            base_speed_factor = 1.12
    else:
        base_speed_factor = 1.12
        
    characters_map = {c["id"]: c for c in script_data.get("characters", [])}
    audio_dir = job_dir / "audio"
    audio_dir.mkdir(exist_ok=True)

    # --- Step 1: Generate each scene individually ---
    results = []
    for i, scene in enumerate(scenes):
        if progress_callback:
            progress_callback(i / num_scenes, f"🎙️ 나레이션 생성 중... ({i+1}/{num_scenes})")
            
        char_id = scene.get("character_id", "char_1")
        char_info = characters_map.get(char_id, {})
        
        result = await generate_narration(
            text=scene["script"],
            scene_id=scene["scene_id"],
            job_dir=job_dir,
            character_id=char_id,
            gender=char_info.get("voice_category", "female"),
            role="teacher" if "teacher" in char_id else "student",
            age_group=char_info.get("age_group", "young-adult"),
            speed=base_speed_factor,
        )
        results.append(result)
        logger.info(f"[TTS] Scene {scene['scene_id']} done: {result['duration']:.2f}s")

    # --- Step 2: Batch normalization for consistency ---
    if progress_callback:
        progress_callback(0.85, "🔊 오디오 볼륨 최적화 및 페이드 효과 적용 중...")
    
    logger.info(
        f"[NarrationSpeed] scene_count={num_scenes}, "
        f"base_speed_factor={base_speed_factor:.2f}"
    )
    if progress_callback and base_speed_factor > 1.01:
        progress_callback(0.87, f"⚡ 정보량 기준 기본 나레이션 속도 {base_speed_factor:.2f}배 적용 중...")

    filters = "loudnorm"
    fade_dur = 0.03  # 30ms fade to prevent clicks
    
    for i, result in enumerate(results):
        if not result["path"]:
            continue
            
        audio_path = Path(result["path"])
        if not audio_path.exists():
            continue
        
        # Step 2a: Normalize + slight speed up
        norm_path = audio_path.with_name(f"{audio_path.stem}_norm.mp3")
        try:
            await asyncio.to_thread(
                subprocess.run,
                ["ffmpeg", "-y", "-i", str(audio_path), "-af", filters, str(norm_path)],
                capture_output=True, check=True
            )

            if norm_path.exists():
                audio_path.unlink()
                norm_path.rename(audio_path)
        except Exception as e:
            logger.warning(f"[BatchNorm] Normalization failed for {audio_path.name}: {e}")

        # Step 2b: Add fade-in/out to prevent clicking
        dur = await asyncio.to_thread(get_audio_duration, str(audio_path))
        if dur > 0:
            fade_path = audio_path.with_name(f"{audio_path.stem}_fade.mp3")
            fade_filters = f"afade=t=in:st=0:d={fade_dur}"
            if dur > fade_dur:
                fade_filters += f",afade=t=out:st={dur-fade_dur}:d={fade_dur}"

            try:
                await asyncio.to_thread(
                    subprocess.run,
                    ["ffmpeg", "-y", "-i", str(audio_path), "-af", fade_filters,
                     "-c:a", "libmp3lame", "-b:a", "192k", str(fade_path)],
                    capture_output=True, check=True
                )

                if fade_path.exists():
                    audio_path.unlink()
                    fade_path.rename(audio_path)
            except Exception as e:
                logger.warning(f"[BatchNorm] Fade failed for {audio_path.name}: {e}")

        # Update duration after processing
        final_dur = await asyncio.to_thread(get_audio_duration, str(audio_path))
        results[i]["duration"] = final_dur
        logger.info(f"[BatchNorm] Scene {scenes[i]['scene_id']}: {final_dur:.2f}s")

    # --- Step 3: Shorts duration guard (strict 60s cap) ---
    # All shorts types must stay within the configured 60-second-oriented window.
    SHORTS_MIN = float(duration_target["min_seconds"])
    SHORTS_MAX = float(duration_target["max_seconds"])
    
    total_audio = sum(r["duration"] for r in results if r["path"])
    msg = f"⏱️ 전체 오디오 길이: {total_audio:.2f}초"
    if progress_callback: progress_callback(0.9, msg)
    logger.info(f"[DurationGuard] {msg} (target: {SHORTS_MIN}~{SHORTS_MAX}s)")
    
    if total_audio > SHORTS_MAX or total_audio < SHORTS_MIN:
        if total_audio > SHORTS_MAX:
            # Speed up to fit within limit
            speed_factor = total_audio / SHORTS_MAX
            speed_factor = min(speed_factor, 1.5)  # cap at 1.5x to avoid chipmunk effect
            msg = f"⚡ 오디오가 너무 깁니다. 추가 {speed_factor:.2f}배속 조절 중..."
        else:
            # Slow down to reach minimum
            speed_factor = total_audio / SHORTS_MIN
            speed_factor = max(speed_factor, 0.75)  # cap at 0.75x to avoid too slow
            msg = f"⏳ 오디오가 너무 짧습니다. 추가 {speed_factor:.2f}배속 조절 중..."
            
        if progress_callback: progress_callback(0.95, msg)
        logger.info(f"[DurationGuard] {msg}")
        
        for i, result in enumerate(results):
            if not result["path"]:
                continue
            audio_path = Path(result["path"])
            if not audio_path.exists():
                continue
            
            adjusted_path = audio_path.with_name(f"{audio_path.stem}_adj.mp3")
            try:
                await asyncio.to_thread(
                    subprocess.run,
                    ["ffmpeg", "-y", "-i", str(audio_path),
                     "-af", f"atempo={speed_factor:.4f}",
                     "-c:a", "libmp3lame", "-b:a", "192k",
                     str(adjusted_path)],
                    capture_output=True, check=True
                )
                if adjusted_path.exists():
                    audio_path.unlink()
                    adjusted_path.rename(audio_path)
                    results[i]["duration"] = await asyncio.to_thread(get_audio_duration, str(audio_path))
            except Exception as e:
                logger.warning(f"[DurationGuard] Adjustment failed for {audio_path.name}: {e}")
        
        new_total = sum(r["duration"] for r in results if r["path"])
        logger.info(f"[DurationGuard] Adjusted total: {new_total:.2f}s")

    return results


def get_audio_duration(audio_path: str) -> float:
    """Get actual audio duration using ffprobe."""
    import json as json_lib

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
        info = json_lib.loads(result.stdout)
        return float(info["format"]["duration"])
    except Exception:
        return 5.0  # fallback default
