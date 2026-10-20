"""Local Uyghur speech recognition using Rekipjan's merged Whisper model."""

import io
import math
import os
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "models" / "whisper-small-uyghur-merged"
MODEL_ID = "Rekipjan/whisper-small-uyghur"
SAMPLE_RATE = 16_000
MAX_DURATION_SECONDS = 120

_pipeline = None
_pipeline_lock = threading.Lock()
_inference_lock = threading.Lock()


def get_pipeline():
    """Load the model once; downloads happen in install-asr.ps1, not in requests."""
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    with _pipeline_lock:
        if _pipeline is not None:
            return _pipeline
        model_dir = Path(os.environ.get("UYGHUR_ASR_MODEL_DIR", str(MODEL_DIR)))
        if not (model_dir / "model.safetensors").is_file():
            raise RuntimeError("维语识别模型尚未安装。请先运行 .\\install-asr.ps1 下载模型。")
        try:
            import torch
            from transformers import pipeline
        except ImportError as exc:
            raise RuntimeError("缺少维语识别依赖。请先运行 .\\install-asr.ps1。") from exc
        device = 0 if torch.cuda.is_available() else -1
        try:
            _pipeline = pipeline(
                "automatic-speech-recognition",
                model=str(model_dir),
                device=device,
                torch_dtype=torch.float16 if device == 0 else torch.float32,
                chunk_length_s=30,
            )
        except Exception as exc:
            raise RuntimeError(f"维语识别模型加载失败：{exc}") from exc
        return _pipeline


def transcribe_audio(audio_bytes: bytes) -> str:
    """Decode an MP3 or WAV file, resample to 16 kHz and return Uyghur text."""
    try:
        import numpy as np
        import soundfile as sf
        from scipy.signal import resample_poly
    except ImportError as exc:
        raise RuntimeError("缺少音频处理依赖。请先运行 .\\install-asr.ps1。") from exc

    try:
        info = sf.info(io.BytesIO(audio_bytes))
    except (RuntimeError, ValueError) as exc:
        raise RuntimeError("音频无法解码，请上传标准 MP3 或 WAV 文件。") from exc
    if info.duration > MAX_DURATION_SECONDS:
        raise RuntimeError("音频不能超过 2 分钟。")
    try:
        audio, sample_rate = sf.read(io.BytesIO(audio_bytes), dtype="float32", always_2d=True)
    except (RuntimeError, ValueError) as exc:
        raise RuntimeError("音频无法解码，请上传标准 MP3 或 WAV 文件。") from exc
    if sample_rate <= 0 or len(audio) == 0:
        raise RuntimeError("音频为空或采样率无效。")
    if len(audio) / sample_rate > MAX_DURATION_SECONDS:
        raise RuntimeError("音频不能超过 2 分钟。")
    audio = audio.mean(axis=1)
    if sample_rate != SAMPLE_RATE:
        divisor = math.gcd(sample_rate, SAMPLE_RATE)
        audio = resample_poly(audio, SAMPLE_RATE // divisor, sample_rate // divisor)
    audio = np.asarray(audio, dtype=np.float32)

    recognizer = get_pipeline()
    # The model card uses Uzbek as the merged model's language token for Uyghur.
    language = os.environ.get("UYGHUR_ASR_LANGUAGE", "uzbek").strip() or "uzbek"
    try:
        with _inference_lock:
            result = recognizer(
                {"array": audio, "sampling_rate": SAMPLE_RATE},
                generate_kwargs={"language": language, "task": "transcribe"},
            )
    except Exception as exc:
        raise RuntimeError(f"维语识别失败：{exc}") from exc
    transcription = result.get("text", "").strip() if isinstance(result, dict) else ""
    if not transcription:
        raise RuntimeError("没有识别出文字，请换一段清晰的维语录音重试。")
    return transcription


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="使用本地 Whisper 模型识别维语 MP3/WAV")
    parser.add_argument("audio", type=Path, help="MP3 或 WAV 文件路径")
    args = parser.parse_args()
    print(transcribe_audio(args.audio.read_bytes()))
