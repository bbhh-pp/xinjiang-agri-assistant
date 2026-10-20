"""Non-destructive pre-release checks for the production container."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_SECRETS = (
    "SHENNONG_API_KEY", "TENCENT_TOKENHUB_API_KEY",
    "XFYUN_TTS_APP_ID", "XFYUN_TTS_API_KEY", "XFYUN_TTS_API_SECRET",
)


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    print("[1/6] Python production dependencies")
    try:
        import uvicorn  # noqa: F401
        import onnxruntime  # noqa: F401
        import numpy  # noqa: F401
        print("  Uvicorn, ONNX Runtime and NumPy are importable.")
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        version = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True, timeout=10)
        if version.returncode:
            errors.append("FFmpeg binary could not run.")
        else:
            print("  FFmpeg executable starts successfully.")
    except Exception as exc:
        errors.append(f"ASGI/ASR dependency check failed: {type(exc).__name__}.")

    print("[2/6] Linux model artifact")
    model = Path(os.environ.get("UYGHUR_ASR_MODEL_PATH", "/opt/shennong/models/uyghur_asr.onnx"))
    if model.is_file() and model.stat().st_size >= 200_000_000:
        print(f"  ONNX model exists ({model.stat().st_size // (1024 * 1024)} MiB).")
        try:
            import onnxruntime as ort
            session = ort.InferenceSession(str(model), providers=["CPUExecutionProvider"])
            inputs = [item.name for item in session.get_inputs()]
            outputs = [item.name for item in session.get_outputs()]
            if "input" not in inputs or "output" not in outputs:
                errors.append("ONNX model input/output names do not match the recognizer.")
            else:
                print("  CPU ONNX session loads and exposes expected input/output names.")
        except Exception as exc:
            errors.append(f"CPU ONNX session failed to load: {type(exc).__name__}.")
    else:
        errors.append("UYGHUR_ASR_MODEL_PATH does not point to the pinned ONNX model.")

    print("[3/6] Persistent SQLite")
    db_path = Path(os.environ.get("SHENNONG_CONVERSATIONS_DB", "/var/lib/shennong/conversations.sqlite3"))
    if db_path.is_file():
        try:
            import sqlite3
            with sqlite3.connect(db_path) as db:
                check = db.execute("PRAGMA quick_check").fetchone()[0]
                tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if check != "ok" or not {"users", "conversations", "turns"}.issubset(tables):
                errors.append("Persistent database integrity/schema check failed.")
            else:
                print("  Persistent database passes quick_check and has account/history tables.")
        except Exception as exc:
            errors.append(f"Database check failed: {type(exc).__name__}.")
    else:
        errors.append("Persistent database is missing; initialize or migrate it before serving.")

    print("[4/6] Production origin and server secrets")
    origin = os.environ.get("SHENNONG_PUBLIC_ORIGIN", "")
    if not re.fullmatch(r"https://[^/\s]+", origin):
        errors.append("SHENNONG_PUBLIC_ORIGIN must be a bare https:// domain origin.")
    else:
        print("  HTTPS origin is configured.")
    missing = [name for name in REQUIRED_SECRETS if not os.environ.get(name, "").strip()]
    if missing:
        errors.append("Server environment is missing: " + ", ".join(missing))
    else:
        placeholders = [name for name in REQUIRED_SECRETS
                        if os.environ.get(name, "").strip().lower() in {
                            "configure-on-server", "your-key", "replace-me", "changeme"}]
        if placeholders:
            errors.append("Replace deployment-example values for: " + ", ".join(placeholders))
        else:
            print("  Required API credential variables are present; values were not displayed.")

    print("[5/6] Frontend asset credential scan")
    secret_patterns = (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), re.compile(r"AKID[A-Za-z0-9]{12,}"))
    frontend = [ROOT / "web" / name for name in ("index.html", "app.js", "ui_locale.js", "styles.css", "grassland.css")]
    for path in frontend:
        if not path.is_file():
            errors.append(f"Missing frontend asset: {path.name}.")
            continue
        content = path.read_text(encoding="utf-8")
        if any(pattern.search(content) for pattern in secret_patterns):
            errors.append(f"Potential credential-shaped value found in frontend asset: {path.name}.")
    if not errors:
        print("  Required frontend assets exist; no common credential-shaped values found.")

    print("[6/6] Single-instance and quota policy")
    try:
        minute = int(os.environ.get("SHENNONG_REQUESTS_PER_MINUTE", "6"))
        daily = int(os.environ.get("SHENNONG_DAILY_REQUESTS", "20"))
        if not 1 <= minute <= 60 or not 1 <= daily <= 500:
            errors.append("Configured per-user quotas are outside supported bounds.")
        else:
            print(f"  Per-account caps set: {minute}/minute, {daily}/day; deploy one app instance for SQLite.")
    except ValueError:
        errors.append("Quota values must be integers.")

    for warning in warnings:
        print("WARNING: " + warning)
    if errors:
        for error in errors:
            print("FAIL: " + error, file=sys.stderr)
        return 1
    print("Release checks passed. This checks readiness only; it does not publish the website.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
