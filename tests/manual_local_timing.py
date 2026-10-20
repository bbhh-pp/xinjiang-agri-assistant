import time
from pathlib import Path

from gheyret_uyghur_asr import recognize_audio
from uyghur_agri_lexicon import correct_transcription


audio = (Path(__file__).resolve().parents[1] / "慢速.mp3").read_bytes()
started = time.perf_counter()
transcription, inference = recognize_audio(audio)
asr = time.perf_counter() - started
started = time.perf_counter()
result = correct_transcription(transcription)
glossary = time.perf_counter() - started
print(f"ASR_WALL_SECONDS={asr:.2f}")
print(f"ASR_INFERENCE_SECONDS={inference:.2f}")
print(f"GLOSSARY_SECONDS={glossary:.4f}")
print(f"GLOSSARY_MATCHES={len(result['corrections'])}")
print(f"GLOSSARY_LOADED={result['glossary_loaded']}")
