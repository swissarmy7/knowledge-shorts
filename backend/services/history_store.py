"""
Persistent history storage for generated shorts.
"""
import json
import uuid
from datetime import datetime, timezone

from backend.config import BASE_DIR

HISTORY_DIR = BASE_DIR / "output" / "history"
HISTORY_FILE = HISTORY_DIR / "video_history.json"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []

    try:
        with HISTORY_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []

    return data if isinstance(data, list) else []


def _write_history(items: list[dict]) -> None:
    with HISTORY_FILE.open("w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def _extract_video_title(script_data: dict) -> str:
    video_title = script_data.get("video_title", "")
    if isinstance(video_title, dict):
        return f"{video_title.get('highlight', '')} {video_title.get('rest', '')}".strip()
    return str(video_title or "").strip()


def _extract_topic(script_data: dict) -> str:
    return (
        script_data.get("topic")
        or script_data.get("subject")
        or script_data.get("situation_setting", {}).get("concept")
        or _extract_video_title(script_data)
    )


def build_history_entry(job_id: str, script_data: dict, video_url: str) -> dict:
    return {
        "id": uuid.uuid4().hex[:12],
        "job_id": job_id,
        "created_at": _now_iso(),
        "topic": _extract_topic(script_data),
        "subject": script_data.get("subject", ""),
        "video_title": _extract_video_title(script_data),
        "youtube_title": script_data.get("youtube_title", ""),
        "youtube_description": script_data.get("youtube_description", ""),
        "youtube_tags": script_data.get("youtube_tags", []),
        "situation": script_data.get("situation_setting", {}).get("situation", ""),
        "scene_count": len(script_data.get("scenes", [])),
        "video_url": video_url,
        "script_data": script_data,
    }


def save_history_entry(entry: dict) -> dict:
    history = _read_history()
    history = [item for item in history if item.get("job_id") != entry.get("job_id")]
    history.insert(0, entry)
    _write_history(history)
    return entry


def list_history_entries() -> list[dict]:
    return _read_history()


def get_history_entry(entry_id: str):
    history = _read_history()
    return next((item for item in history if item.get("id") == entry_id), None)


def delete_history_entry(entry_id: str):
    history = _read_history()
    deleted_item = next((item for item in history if item.get("id") == entry_id), None)
    if not deleted_item:
        return None

    _write_history([item for item in history if item.get("id") != entry_id])
    return deleted_item
