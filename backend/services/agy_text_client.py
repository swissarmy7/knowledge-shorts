"""
agy text generation bridge for the shorts backend.

The backend often runs inside Docker while the agy CLI is available on the host.
This module writes JSON requests to the shared output directory and waits for a
host-side worker to invoke agy and write the response back.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from backend.config import (
    OUTPUT_DIR,
    AGY_TEXT_TIMEOUT,
    AGY_TEXT_REQUEST_TIMEOUT,
    AGY_TEXT_POLL_INTERVAL,
)


TEXT_REQUEST_DIR = OUTPUT_DIR / "agy_text_requests"


def _sanitize_request_id(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-.")
    return clean[:96] or "codex-text"


def build_agy_text_request(
    *,
    prompt: str,
    request_id: str,
    system_instruction: str = "",
    response_mime_type: str = "text/plain",
    temperature: float | None = None,
) -> dict[str, Any]:
    return {
        "request_id": _sanitize_request_id(request_id),
        "prompt": prompt,
        "system_instruction": system_instruction,
        "response_mime_type": response_mime_type,
        "temperature": temperature,
        "codex_timeout_sec": AGY_TEXT_TIMEOUT,
        # Kept for compatibility with older workers that may still be running.
        "agy_timeout_sec": AGY_TEXT_TIMEOUT,
    }


def write_agy_text_request(
    *,
    prompt: str,
    request_id: str,
    system_instruction: str = "",
    response_mime_type: str = "text/plain",
    temperature: float | None = None,
) -> tuple[Path, Path]:
    TEXT_REQUEST_DIR.mkdir(parents=True, exist_ok=True)
    safe_request_id = _sanitize_request_id(request_id)
    payload = build_agy_text_request(
        prompt=prompt,
        request_id=safe_request_id,
        system_instruction=system_instruction,
        response_mime_type=response_mime_type,
        temperature=temperature,
    )
    req_path = TEXT_REQUEST_DIR / f"{safe_request_id}.request.json"
    res_path = TEXT_REQUEST_DIR / f"{safe_request_id}.response.json"
    req_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return req_path, res_path


def resolve_agy_text_response(response: dict[str, Any]) -> str:
    if response.get("status") != "ok":
        raise ValueError(f"codex text error: {response.get('error', 'unknown')}")
    text = response.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("agy text response is empty")
    return text.strip()


async def generate_text_with_agy(
    prompt: str,
    *,
    system_instruction: str = "",
    response_mime_type: str = "text/plain",
    temperature: float | None = None,
    purpose: str = "text",
) -> str:
    """Generate text by round-tripping through the host Codex worker."""
    digest = hashlib.md5(
        f"{purpose}|{response_mime_type}|{system_instruction}|{prompt}".encode("utf-8")
    ).hexdigest()[:16]
    request_id = _sanitize_request_id(f"{purpose}-{digest}-{int(time.time() * 1000)}")
    req_path, res_path = write_agy_text_request(
        prompt=prompt,
        request_id=request_id,
        system_instruction=system_instruction,
        response_mime_type=response_mime_type,
        temperature=temperature,
    )

    deadline = time.monotonic() + AGY_TEXT_REQUEST_TIMEOUT
    while time.monotonic() < deadline:
        if res_path.exists():
            break
        await asyncio.sleep(AGY_TEXT_POLL_INTERVAL)
    else:
        req_path.unlink(missing_ok=True)
        raise TimeoutError(f"codex text timeout (request_id={request_id})")

    response = json.loads(res_path.read_text(encoding="utf-8"))
    return resolve_agy_text_response(response)
