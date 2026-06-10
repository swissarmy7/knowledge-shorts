"""
Subtitle Generator Service
Creates SRT subtitle files from scene scripts.
"""
from pathlib import Path


def _format_srt_time(seconds: float) -> str:
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_subtitles(
    scenes: list[dict],
    durations: list[float],
    job_dir: Path,
) -> str:
    """Generate SRT subtitle file from scenes and their durations."""
    subtitle_dir = job_dir / "subtitles"
    subtitle_dir.mkdir(exist_ok=True)
    srt_path = subtitle_dir / "subtitles.srt"

    srt_content = ""
    current_time = 0.0

    import re
    for i, (scene, duration) in enumerate(zip(scenes, durations)):
        script = re.sub(r'\([^)]*\)', '', scene["script"]).strip()
        
        # Actual audio duration might be less than scene duration (due to 0.4s buffer)
        # We want the subtitle to end when the audio ends, or slightly before.
        # Typically narration entries in 'scenes' have 'audio_duration' if we store it
        audio_duration = scene.get("audio_duration", duration - 0.4 if duration > 0.4 else duration)
        
        start_time = current_time
        end_time = current_time + audio_duration

        # Break long scripts into 2-line chunks for readability
        words = script.split()
        mid = len(words) // 2
        if len(words) > 8:
            line1 = " ".join(words[:mid])
            line2 = " ".join(words[mid:])
            subtitle_text = f"{line1}\n{line2}"
        else:
            subtitle_text = script

        srt_content += f"{i + 1}\n"
        srt_content += f"{_format_srt_time(start_time)} --> {_format_srt_time(end_time)}\n"
        srt_content += f"{subtitle_text}\n\n"

        current_time = end_time

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    return str(srt_path)
