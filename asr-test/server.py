"""Independent local test page for gheyret's Uyghur ONNX ASR model.

This does not call Shennong or change the main assistant's recognition route.
Model source: https://github.com/gheyret/uyghurasr_python
"""

import base64
import binascii
import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
MODEL = ROOT / "model" / "uyghur_asr.onnx"
PAGE = ROOT / "index.html"
MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_REQUEST_BYTES = 11 * 1024 * 1024
MAX_SECONDS = 45
SAMPLE_RATE = 22_050
VOCAB = ["<pad>", "<sos>", "<eos>"] + list("abcdefghijklmnopqrstuvwxyz éöü’")

_session = None
_session_lock = threading.Lock()
_inference_lock = threading.Lock()


def get_session():
    global _session
    if _session is not None:
        return _session
    with _session_lock:
        if _session is not None:
            return _session
        if not MODEL.is_file() or MODEL.stat().st_size < 1_000_000:
            raise RuntimeError("尚未安装开源识别模型，请先运行本目录的 install-model.ps1。")
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise RuntimeError("缺少 onnxruntime，请先运行本目录的 install-model.ps1。") from exc
        _session = ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])
        return _session


def recognize(audio_bytes: bytes) -> tuple[str, float]:
    try:
        import numpy as np
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("缺少音频处理依赖，请先运行本目录的 install-model.ps1。") from exc
    try:
        decoded = subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
             "-i", "pipe:0", "-t", str(MAX_SECONDS + 1), "-ac", "1", "-ar", str(SAMPLE_RATE),
             "-f", "f32le", "-acodec", "pcm_f32le", "pipe:1"],
            input=audio_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=40, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("音频解码超时，请换一段较短的录音。") from exc
    if decoded.returncode != 0 or not decoded.stdout:
        raise RuntimeError("无法读取音频；请选择有效的 MP3 或 WAV 文件。")
    audio = np.frombuffer(decoded.stdout, dtype="<f4").copy()
    if len(audio) > SAMPLE_RATE * MAX_SECONDS:
        raise RuntimeError(f"录音不能超过 {MAX_SECONDS} 秒。")

    session = get_session()
    started = time.perf_counter()
    try:
        with _inference_lock:
            logits = session.run(["output"], {"input": audio})[0]
    except Exception as exc:
        raise RuntimeError(f"模型推理失败：{exc}") from exc
    elapsed = time.perf_counter() - started
    ids = np.argmax(logits, axis=1)
    if ids.ndim != 2 or ids.shape[0] != 1:
        raise RuntimeError("模型返回了无法解析的结果。")
    letters = []
    previous = None
    for item in ids[0]:
        index = int(item)
        if index >= len(VOCAB):
            raise RuntimeError("模型输出的字符编号超出词表。")
        if index != 0 and index != previous:
            letters.append(VOCAB[index])
        previous = index
    transcription = "".join(letters).strip()
    if not transcription:
        raise RuntimeError("模型没有识别出文字；请换一段清晰的维语录音。")
    return transcription, elapsed


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status: int, value: dict) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/status":
            try:
                import importlib.util
                dependencies_ready = all(importlib.util.find_spec(name) for name in ("onnxruntime", "numpy", "imageio_ffmpeg"))
            except Exception:
                dependencies_ready = False
            self.send_json(200, {"ready": MODEL.is_file() and MODEL.stat().st_size > 1_000_000 and dependencies_ready,
                                 "decoder": "ffmpeg"})
            return
        if path != "/":
            self.send_error(404)
            return
        body = PAGE.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/api/recognize":
            self.send_error(404)
            return
        origin = self.headers.get("Origin")
        expected = f"http://127.0.0.1:{self.server.server_port}"
        if origin and origin != expected:
            self.send_json(403, {"error": "请从本地测试页面提交录音。"})
            return
        if self.headers.get_content_type() != "application/json":
            self.send_json(415, {"error": "请求格式应为 JSON。"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            size = 0
        if size < 1 or size > MAX_REQUEST_BYTES:
            self.send_json(413, {"error": "录音不能超过 8 MB。"})
            return
        try:
            payload = json.loads(self.rfile.read(size))
            encoded = payload["audio_base64"]
            if not isinstance(encoded, str):
                raise ValueError()
            audio_bytes = base64.b64decode(encoded, validate=True)
        except (KeyError, TypeError, ValueError, binascii.Error, json.JSONDecodeError):
            self.send_json(400, {"error": "录音数据无法读取。"})
            return
        if not audio_bytes or len(audio_bytes) > MAX_AUDIO_BYTES:
            self.send_json(413, {"error": "录音不能超过 8 MB。"})
            return
        try:
            transcription, seconds = recognize(audio_bytes)
        except RuntimeError as exc:
            self.send_json(503, {"error": str(exc)})
            return
        self.send_json(200, {"transcription": transcription, "inference_seconds": round(seconds, 2)})


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8766), Handler)
    print("维语开源识别测试页：http://127.0.0.1:8766/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
