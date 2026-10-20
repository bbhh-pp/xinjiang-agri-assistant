"""Local ONNX Uyghur ASR engine used by both the test page and main app."""

import subprocess
import os
import shutil
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MODEL = Path(os.environ.get("UYGHUR_ASR_MODEL_PATH", str(ROOT / "asr-test" / "model" / "uyghur_asr.onnx")))
MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_SECONDS = 45
SAMPLE_RATE = 22_050
VOCAB = ["<pad>", "<sos>", "<eos>"] + list("abcdefghijklmnopqrstuvwxyz éöü’")
LATIN_DIGRAPHS = {
    "ch": "چ", "gh": "غ", "sh": "ش", "zh": "ژ", "ng": "ڭ",
}
LATIN_LETTERS = {
    "a": "ا", "b": "ب", "c": "چ", "d": "د", "e": "ە", "f": "ف",
    "g": "گ", "h": "ھ", "i": "ى", "j": "ج", "k": "ك", "l": "ل",
    "m": "م", "n": "ن", "o": "و", "p": "پ", "q": "ق", "r": "ر",
    "s": "س", "t": "ت", "u": "ۇ", "v": "ئ", "w": "ۋ", "x": "خ",
    "y": "ي", "z": "ز", "é": "ې", "ë": "ې", "ä": "ە", "ö": "ۆ", "ü": "ۈ",
}
LATIN_VOWELS = frozenset("aeiouöüéë")

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
            raise RuntimeError("尚未安装维语识别模型，请先运行 asr-test\\install-model.cmd。")
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise RuntimeError("缺少 onnxruntime，请先运行 asr-test\\install-model.cmd。") from exc
        _session = ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])
        return _session


def _ffmpeg_executable() -> str:
    """Prefer the OS FFmpeg package (including Linux ARM64 deployments)."""
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("未找到 FFmpeg，请安装系统 FFmpeg 或 imageio-ffmpeg。") from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def recognize_audio(audio_bytes: bytes) -> tuple[str, float]:
    """Decode browser-recorded audio and return Latin Uyghur plus inference time."""
    if not audio_bytes or len(audio_bytes) > MAX_AUDIO_BYTES:
        raise RuntimeError("录音为空或超过 8 MB。")
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("缺少音频解码依赖，请先运行 asr-test\\install-model.cmd。") from exc

    try:
        decoded = subprocess.run(
            [_ffmpeg_executable(), "-hide_banner", "-loglevel", "error",
             "-i", "pipe:0", "-t", str(MAX_SECONDS + 1), "-ac", "1", "-ar", str(SAMPLE_RATE),
             "-f", "f32le", "-acodec", "pcm_f32le", "pipe:1"],
            input=audio_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=40, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("音频解码超时，请缩短录音后重试。") from exc
    if decoded.returncode != 0 or not decoded.stdout:
        raise RuntimeError("无法读取录音，请重新录制后重试。")
    audio = np.frombuffer(decoded.stdout, dtype="<f4").copy()
    if len(audio) > SAMPLE_RATE * MAX_SECONDS:
        raise RuntimeError(f"录音不能超过 {MAX_SECONDS} 秒。")

    session = get_session()
    started = time.perf_counter()
    try:
        with _inference_lock:
            logits = session.run(["output"], {"input": audio})[0]
    except Exception as exc:
        raise RuntimeError(f"维语模型识别失败：{exc}") from exc
    elapsed = time.perf_counter() - started
    ids = np.argmax(logits, axis=1)
    if ids.ndim != 2 or ids.shape[0] != 1:
        raise RuntimeError("模型返回了无法解析的结果。")
    letters = []
    previous = None
    for item in ids[0]:
        index = int(item)
        if index >= len(VOCAB):
            raise RuntimeError("模型输出字符超出词表。")
        if index != 0 and index != previous:
            letters.append(VOCAB[index])
        previous = index
    transcription = "".join(letters).strip()
    if not transcription:
        raise RuntimeError("没有识别出文字，请说得清楚一些后重试。")
    return transcription, elapsed


def latin_to_uyghur_arabic(text: str) -> str:
    """Map the model's ULY-like Latin spelling to the Uyghur Arabic alphabet.

    The model vocabulary uses é for the vowel otherwise commonly written ë.
    """
    converted_words = []
    for word in text.split():
        lowered = word.casefold()
        output = []
        index = 0
        if lowered and lowered[0] in LATIN_VOWELS:
            output.append("ئ")
        while index < len(lowered):
            if lowered[index] in {"'", "’", "ʼ"}:
                index += 1
                continue
            pair = lowered[index:index + 2]
            if pair in LATIN_DIGRAPHS:
                output.append(LATIN_DIGRAPHS[pair])
                index += 2
                continue
            output.append(LATIN_LETTERS.get(lowered[index], lowered[index]))
            index += 1
        converted_words.append("".join(output))
    return " ".join(converted_words)
