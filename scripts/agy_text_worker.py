#!/usr/bin/env python3
"""
Host-side Codex text worker.

Watches output/agy_text_requests/ for *.request.json files written by the Docker
backend, invokes the host Codex CLI, then writes a *.response.json so the backend
can pick up the generated text.

Run on the host (not inside Docker):
    python3 scripts/agy_text_worker.py [--watch-dir /path/to/output/agy_text_requests]
"""
import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [codex-text-worker] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("codex-text-worker")

BASE_DIR = Path("/var/www/html/my_shorts").resolve()
DEFAULT_WATCH_DIR = Path("/var/www/html/my_shorts/output/agy_text_requests")
CODEX_BIN = shutil.which("codex") or os.path.expanduser("~/.local/bin/codex")
CODEX_MODEL = (os.getenv("CODEX_TEXT_MODEL") or os.getenv("CODEX_MODEL") or "").strip()
PROCESS_TIMEOUT = int(os.getenv("CODEX_TEXT_WORKER_TIMEOUT") or os.getenv("AGY_TEXT_WORKER_TIMEOUT", "300"))
POLL_INTERVAL = float(os.getenv("CODEX_TEXT_WORKER_POLL") or os.getenv("AGY_TEXT_WORKER_POLL", "2.0"))


def _build_codex_prompt(payload: dict) -> str:
    system_instruction = (payload.get("system_instruction") or "").strip()
    prompt = (payload.get("prompt") or "").strip()
    response_mime_type = (payload.get("response_mime_type") or "text/plain").strip()

    parts = [
        "You are generating content for the shorts generator backend.",
        "Do not ask questions. Produce the requested output now.",
    ]
    if response_mime_type == "application/json":
        parts.extend([
            "Return ONLY valid JSON text.",
            "Do not wrap it in markdown fences.",
            "Do not include commentary before or after the JSON.",
        ])
    else:
        parts.append("Return only the requested text, without meta commentary.")

    if system_instruction:
        parts.append("\n[System instruction]\n" + system_instruction)
    parts.append("\n[User prompt]\n" + prompt)
    return "\n".join(parts)


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _write_response(res_path: Path, **fields) -> None:
    res_path.write_text(json.dumps(fields, ensure_ascii=False, indent=2), encoding="utf-8")


def _codex_exec_cmd(prompt: str, output_file: Path) -> list[str]:
    cmd = [
        CODEX_BIN,
        "exec",
        "--cd",
        str(BASE_DIR),
        "--output-last-message",
        str(output_file),
        "--dangerously-bypass-approvals-and-sandbox",
    ]
    if CODEX_MODEL:
        cmd.extend(["--model", CODEX_MODEL])
    cmd.append(prompt)
    return cmd


def run_cmd_nonblock(cmd, timeout):
    import fcntl
    import os

    process = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        close_fds=True
    )

    # Set non-blocking on stdout and stderr raw file descriptors
    fds = []
    for pipe in (process.stdout, process.stderr):
        if pipe:
            fd = pipe.fileno()
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
            fds.append((fd, pipe))

    stdout_bytes = bytearray()
    stderr_bytes = bytearray()

    start_time = time.monotonic()
    while True:
        retcode = process.poll()

        # Read from stdout
        try:
            data = os.read(process.stdout.fileno(), 4096)
            if data:
                stdout_bytes.extend(data)
        except OSError:
            pass

        # Read from stderr
        try:
            data = os.read(process.stderr.fileno(), 4096)
            if data:
                stderr_bytes.extend(data)
        except OSError:
            pass

        if retcode is not None:
            break

        if time.monotonic() - start_time > timeout:
            process.kill()
            process.wait()
            raise subprocess.TimeoutExpired(cmd, timeout, output=stdout_bytes, stderr=stderr_bytes)

        time.sleep(0.1)

    # Final reads to empty the pipe buffer
    for fd, pipe in fds:
        while True:
            try:
                data = os.read(fd, 4096)
                if not data:
                    break
                if pipe == process.stdout:
                    stdout_bytes.extend(data)
                else:
                    stderr_bytes.extend(data)
            except OSError:
                break

    stdout_str = stdout_bytes.decode('utf-8', errors='replace')
    stderr_str = stderr_bytes.decode('utf-8', errors='replace')

    return subprocess.CompletedProcess(
        args=cmd,
        returncode=retcode,
        stdout=stdout_str,
        stderr=stderr_str
    )


def process_request(req_path: Path) -> None:
    stem = req_path.stem.replace(".request", "")
    processing_path = req_path.with_name(f"{stem}.processing.json")
    res_path = req_path.with_name(f"{stem}.response.json")

    try:
        req_path.rename(processing_path)
    except (FileNotFoundError, OSError):
        return

    try:
        payload = json.loads(processing_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Cannot parse {processing_path}: {e}")
        _write_response(res_path, status="error", error=f"bad request JSON: {e}")
        _safe_unlink(processing_path)
        return

    request_id = payload.get("request_id", stem)
    codex_prompt = _build_codex_prompt(payload)
    process_timeout = int(payload.get("codex_timeout_sec") or payload.get("agy_timeout_sec") or PROCESS_TIMEOUT)
    output_file = processing_path.with_name(f"{stem}.codex-output.txt")
    _safe_unlink(output_file)
    logger.info(f"Processing {request_id}")

    try:
        result = run_cmd_nonblock(
            _codex_exec_cmd(codex_prompt, output_file),
            timeout=process_timeout + 30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"codex exited {result.returncode}: {result.stderr[:500]}")
    except subprocess.TimeoutExpired:
        logger.error(f"codex timed out for {request_id}")
        _write_response(res_path, status="error", error="codex process timed out")
        _safe_unlink(processing_path)
        _safe_unlink(output_file)
        return
    except Exception as e:
        logger.error(f"codex invocation failed for {request_id}: {e}")
        _write_response(res_path, status="error", error=str(e))
        _safe_unlink(processing_path)
        _safe_unlink(output_file)
        return

    text = ""
    if output_file.exists():
        text = output_file.read_text(encoding="utf-8").strip()
    if not text:
        text = (result.stdout or "").strip()
    if not text:
        logger.error(f"codex returned empty output for {request_id}")
        _write_response(res_path, status="error", error="empty codex output")
        _safe_unlink(processing_path)
        _safe_unlink(output_file)
        return

    logger.info(f"OK {request_id} ({len(text)} chars)")
    _write_response(res_path, status="ok", text=text)
    _safe_unlink(processing_path)
    _safe_unlink(output_file)


def watch(watch_dir: Path) -> None:
    watch_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Watching {watch_dir} (poll every {POLL_INTERVAL}s)")
    while True:
        for req_path in sorted(watch_dir.glob("*.request.json")):
            try:
                process_request(req_path)
            except Exception as e:
                logger.error(f"Unhandled error processing {req_path}: {e}")
        time.sleep(POLL_INTERVAL)


def main() -> None:
    parser = argparse.ArgumentParser(description="Codex text worker")
    parser.add_argument(
        "--watch-dir",
        type=Path,
        default=DEFAULT_WATCH_DIR,
        help="Directory to watch for *.request.json files",
    )
    args = parser.parse_args()

    if not Path(CODEX_BIN).exists():
        logger.error(f"codex not found at {CODEX_BIN}. Install and authenticate Codex first.")
        sys.exit(1)
    watch(args.watch_dir)


if __name__ == "__main__":
    main()
