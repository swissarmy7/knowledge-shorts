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
from backend.services.google_tts_service import get_voice_name
from backend.services.supertonic_local_service import generate_supertonic_local

logger = logging.getLogger("shorts")

SCENE_DURATION_TARGETS = {
    8: {"min_seconds": 54.0, "max_seconds": 68.0},
    10: {"min_seconds": 80.0, "max_seconds": 96.0},
    12: {"min_seconds": 98.0, "max_seconds": 116.0},
}


def get_duration_target(scene_count: int) -> dict:
    return SCENE_DURATION_TARGETS.get(
        scene_count,
        {
            "min_seconds": max(60.0, scene_count * 7.0),
            "max_seconds": min(110.0, scene_count * 9.0),
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

    base_speed = 1.05

    # Nudge slightly when the script is clearly dense; never exceed 1.15.
    if avg_chars >= 55:
        base_speed += 0.03
    if avg_chars >= 80:
        base_speed += 0.03

    return min(base_speed, 1.15)


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
) -> dict:
    """Generate TTS narration for a single scene using Google Cloud TTS Chirp 3.0 HD."""
    audio_dir = job_dir / "audio"
    audio_dir.mkdir(exist_ok=True)

    audio_filename = f"narration_{scene_id}.mp3"
    audio_path = audio_dir / audio_filename

    # Clean text 
    clean_text = clean_narration_text(text)

    # Select Chirp 3.0 HD voice (we still use the mapping but supertonic_local will map it to its own styles)
    voice_name = get_voice_name(character_id, gender, role, age_group)
    
    success = await generate_supertonic_local(
        text=clean_text, 
        voice_name=voice_name, 
        output_path=str(audio_path)
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
    duration_target = script_data.get("duration_target") or get_duration_target(num_scenes)
    base_speed_factor = get_base_speed_factor(scenes, num_scenes)
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
    if progress_callback and base_speed_factor > 1.04:
        progress_callback(0.87, f"⚡ 정보량 기준 기본 나레이션 속도 {base_speed_factor:.2f}배 적용 중...")

    filters = f"loudnorm,atempo={base_speed_factor:.4f}"
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

    # --- Step 3: Shorts duration guard (30s ~ 90s) ---
    # YouTube Shorts MUST be under 90 seconds. If total audio exceeds the limit,
    # apply additional atempo speed-up uniformly. If too short, slow down slightly.
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
