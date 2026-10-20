"""Local bilingual agriculture assistant web server."""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from ask_shennong import ask_shennong, inspect_agricultural_image, stream_chinese_agricultural_answer
from conversation_store import (create_conversation, delete_conversation, finish_translation,
                                get_conversation, get_turn, list_conversations, local_user_id,
                                recent_context, save_chinese_turn)
from gheyret_uyghur_asr import latin_to_uyghur_arabic, recognize_audio
from tencent_hymt import TranslationError, translate_chinese_to_uyghur, translate_uyghur_to_chinese
from uyghur_agri_lexicon import (
    GLOSSARY, correct_arabic_text, correct_transcription,
    terminology_for_chinese_text, terminology_from_corrections,
)
from xfyun_tts import TTSFailure, synthesize_uyghur


ROOT = Path(__file__).resolve().parent
BUILD_ID = "local-history-2026-10-20-1"
STATIC_FILES = {
    "/": (ROOT / "web" / "index.html", "text/html; charset=utf-8"),
    "/static/styles.css": (ROOT / "web" / "styles.css", "text/css; charset=utf-8"),
    "/static/grassland.css": (ROOT / "web" / "grassland.css", "text/css; charset=utf-8"),
    "/static/grassland-home.jpg": (ROOT / "web" / "grassland-home.jpg", "image/jpeg"),
    "/static/app.js": (ROOT / "web" / "app.js", "text/javascript; charset=utf-8"),
    "/static/ui_locale.js": (ROOT / "web" / "ui_locale.js", "text/javascript; charset=utf-8"),
    "/static/xinjiang-pasture.png": (ROOT / "web" / "xinjiang-pasture.png", "image/png"),
}
POST_PATHS = {
    "/api/conversations",
    "/api/ask", "/api/ask-stream", "/api/ask-uyghur-text", "/api/ask-uyghur-text-stream",
    "/api/ask-image", "/api/ask-image-stream", "/api/transcribe-uyghur",
    "/api/transcribe-uyghur-stream", "/api/synthesize-uyghur",
}
MAX_REQUEST_BYTES = 8_192
MAX_QUESTION_CHARS = 2_000
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_IMAGE_REQUEST_BYTES = 6 * 1024 * 1024
MAX_IMAGE_QUESTION_CHARS = 500
MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_AUDIO_REQUEST_BYTES = 11 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg": b"\xff\xd8\xff", "image/png": b"\x89PNG\r\n\x1a\n"}
AUDIO_SIGNATURES = {
    "audio/mpeg": ("mp3",), "audio/mp3": ("mp3",), "audio/wav": ("wav",),
    "audio/x-wav": ("wav",), "audio/wave": ("wav",), "audio/webm": ("webm",),
    "audio/ogg": ("ogg",), "audio/mp4": ("mp4",),
}
ARABIC_TEXT_RE = re.compile(r"[\u0600-\u06ff\u0750-\u077f]")


def _key(name: str) -> str:
    return os.environ.get(name, "").strip()


def _translation_terms_for_answer(answer_zh: str, existing=()) -> list[tuple[str, str]]:
    result = list(existing or ())
    for pair in terminology_for_chinese_text(answer_zh):
        if pair not in result:
            result.append(pair)
        if len(result) >= 10:
            break
    return result[:10]


def _log(label: str, **timings: float) -> None:
    details = "，".join(f"{name}={value:.2f}s" for name, value in timings.items())
    print(f"[耗时][{label}] {details}", flush=True)


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status: int, data: dict, headers: dict | None = None) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _same_origin(self) -> bool:
        expected = os.environ.get("SHENNONG_PUBLIC_ORIGIN", f"http://127.0.0.1:{self.server.server_port}").rstrip("/")
        origin = self.headers.get("Origin")
        referer = self.headers.get("Referer")
        fetch_site = self.headers.get("Sec-Fetch-Site")
        if (origin and origin != expected) or (not origin and referer and not referer.startswith(expected + "/")):
            return False
        return fetch_site in (None, "none", "same-origin")

    def begin_event_stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def send_event(self, event: str, data: dict) -> None:
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        self.wfile.write(f"event: {event}\ndata: {payload}\n\n".encode("utf-8"))
        self.wfile.flush()

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/conversations":
            self.send_json(200, {"conversations": list_conversations(local_user_id())})
            return
        if path.startswith("/api/conversations/"):
            conversation = get_conversation(local_user_id(), path.removeprefix("/api/conversations/"))
            self.send_json(200 if conversation else 404, conversation or {"error": "对话不存在。"})
            return
        if path == "/api/health":
            self.send_json(200, {
                "ok": True, "service": "shennong-local", "build": BUILD_ID,
                "streaming_transcription_endpoint": "/api/transcribe-uyghur-stream",
                "uyghur_glossary_entries": len(GLOSSARY),
                "tencent_translation_configured": bool(_key("TENCENT_TOKENHUB_API_KEY")),
                "tencent_model": os.environ.get("TENCENT_HYMT_MODEL", "hy-mt2-plus"),
                "uyghur_tts_configured": all(_key(name) for name in (
                    "XFYUN_TTS_APP_ID", "XFYUN_TTS_API_KEY", "XFYUN_TTS_API_SECRET")),
            })
            return
        item = STATIC_FILES.get(path)
        if item is None:
            self.send_error(404, "Not found")
            return
        file_path, content_type = item
        try:
            body = file_path.read_bytes()
        except OSError:
            self.send_error(500, "Page unavailable")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        # Always revalidate HTML and executable/style assets so desktop and
        # mobile browsers don't keep rendering different cached generations.
        self.send_header("Cache-Control", "no-store" if content_type.startswith("text/html") else "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        retry_translation = re.fullmatch(r"/api/turns/([0-9a-f]{32})/retry-translation", path)
        if path not in POST_PATHS and not retry_translation:
            self.send_error(404, "Not found")
            return
        if not self._same_origin():
            self.send_json(403, {"error": "请求来源不受信任。", "stage": "request"})
            return
        if self.headers.get_content_type() != "application/json":
            self.send_json(415, {"error": "请求格式不正确。", "stage": "request"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            size = 0
        maximum = (MAX_IMAGE_REQUEST_BYTES if "image" in path else
                   MAX_AUDIO_REQUEST_BYTES if "transcribe" in path else
                   16_384 if path == "/api/synthesize-uyghur" else MAX_REQUEST_BYTES)
        if size < 1 or size > maximum:
            self.send_json(413, {"error": "请求内容过大，请缩短文字、录音或照片后重试。", "stage": "request"})
            return
        try:
            payload = json.loads(self.rfile.read(size))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(400, {"error": "请求内容无法读取。", "stage": "request"})
            return
        if path == "/api/conversations":
            self.send_json(201, create_conversation(local_user_id()))
            return
        if retry_translation:
            owner = local_user_id()
            turn = get_turn(owner, retry_translation.group(1))
            if turn is None:
                self.send_json(404, {"error": "这条回答不存在。"})
                return
            if turn["translation_status"] == "complete":
                self.send_json(200, {"answer_ug": turn["answer_ug"]})
                return
            if not _key("TENCENT_TOKENHUB_API_KEY"):
                self.send_json(503, {"error": "腾讯翻译密钥未配置。", "stage": "translation"})
                return
            try:
                answer_ug = translate_chinese_to_uyghur(
                    turn["answer_zh"], _translation_terms_for_answer(turn["answer_zh"]),
                    api_key=_key("TENCENT_TOKENHUB_API_KEY"))
            except TranslationError as exc:
                finish_translation(owner, turn["id"], failed=True)
                self.send_json(502, {"error": f"维文翻译仍未完成：{exc}", "stage": "tencent_zh_to_ug"})
                return
            finish_translation(owner, turn["id"], answer_ug)
            self.send_json(200, {"answer_ug": answer_ug})
            return
        if path == "/api/synthesize-uyghur":
            self.handle_uyghur_synthesis(payload)
        elif path in ("/api/transcribe-uyghur", "/api/transcribe-uyghur-stream"):
            self.handle_uyghur_audio(payload, stream=path.endswith("-stream"))
        elif path in ("/api/ask-uyghur-text", "/api/ask-uyghur-text-stream"):
            self.handle_uyghur_text(payload, stream=path.endswith("-stream"))
        elif path in ("/api/ask-image", "/api/ask-image-stream"):
            self.handle_image(payload, stream=path.endswith("-stream"))
        else:
            self.handle_chinese_text(payload, stream=path.endswith("-stream"))

    def do_DELETE(self) -> None:
        path = urlsplit(self.path).path
        if not path.startswith("/api/conversations/"):
            self.send_error(404, "Not found")
            return
        if not self._same_origin():
            self.send_json(403, {"error": "请求来源不受信任。"})
            return
        deleted = delete_conversation(local_user_id(), path.removeprefix("/api/conversations/"))
        self.send_json(200 if deleted else 404, {"deleted": deleted})

    def conversation_id(self, payload: object) -> str | None:
        value = payload.get("conversation_id") if isinstance(payload, dict) else None
        if value is None:
            return None  # Keep older API clients working without persistence.
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value) or get_conversation(local_user_id(), value) is None:
            self.send_json(404, {"error": "对话不存在，请新建对话后重试。", "stage": "conversation"})
            raise ValueError("invalid conversation")
        return value

    def require_keys(self) -> bool:
        if not _key("SHENNONG_API_KEY"):
            self.send_json(503, {"error": "神农密钥未配置，请设置 SHENNONG_API_KEY。", "stage": "shennong"})
            return False
        if not _key("TENCENT_TOKENHUB_API_KEY"):
            self.send_json(503, {"error": "腾讯 TokenHub 翻译密钥未配置，请设置 TENCENT_TOKENHUB_API_KEY。", "stage": "translation"})
            return False
        return True

    def _sync_answer(self, question_zh: str, terminology=(), *, started: float, extra: dict | None = None,
                     conversation_id: str | None = None, original_input: str = "", input_kind: str = "text",
                     observation: str = "", display_question_zh: str | None = None) -> dict:
        shennong_started = time.perf_counter()
        owner = local_user_id() if conversation_id else None
        history = recent_context(owner, conversation_id) if owner else ()
        answer_zh = (ask_shennong(question_zh, _key("SHENNONG_API_KEY"), history=history)
                     if history else ask_shennong(question_zh, _key("SHENNONG_API_KEY")))
        shennong_seconds = time.perf_counter() - shennong_started
        turn_id = (save_chinese_turn(owner, conversation_id, input_kind=input_kind,
                                    original_input=original_input, question_zh=display_question_zh or question_zh,
                                    answer_zh=answer_zh, observation=observation) if owner else None)
        translation_started = time.perf_counter()
        try:
            answer_ug = translate_chinese_to_uyghur(
                answer_zh, _translation_terms_for_answer(answer_zh, terminology),
                api_key=_key("TENCENT_TOKENHUB_API_KEY"))
        except TranslationError:
            if turn_id: finish_translation(owner, turn_id, failed=True)
            raise
        if turn_id: finish_translation(owner, turn_id, answer_ug)
        zh_ug_seconds = time.perf_counter() - translation_started
        _log("同步问答", shennong_complete=shennong_seconds, zh_to_ug=zh_ug_seconds,
             total=time.perf_counter() - started)
        return {**(extra or {}), "question_zh": display_question_zh or question_zh,
                "answer_zh": answer_zh, "answer_ug": answer_ug, "conversation_id": conversation_id}

    def _stream_answer(self, question_zh: str, terminology=(), *, started: float,
                       extra: dict | None = None, display_question_zh: str | None = None,
                       conversation_id: str | None = None, original_input: str = "",
                       input_kind: str = "text", observation: str = "") -> None:
        public_question = display_question_zh or question_zh
        owner = local_user_id() if conversation_id else None
        history = recent_context(owner, conversation_id) if owner else ()
        self.begin_event_stream()
        if extra:
            for event_name, data in extra.items():
                self.send_event(event_name, data)
        self.send_event("question", {"question_zh": public_question})
        answer_parts: list[str] = []
        first_token_seconds: float | None = None
        shennong_started = time.perf_counter()
        try:
            source = (stream_chinese_agricultural_answer(question_zh, _key("SHENNONG_API_KEY"), history=history)
                      if history else stream_chinese_agricultural_answer(question_zh, _key("SHENNONG_API_KEY")))
            for chunk in source:
                if first_token_seconds is None:
                    first_token_seconds = time.perf_counter() - shennong_started
                answer_parts.append(chunk)
                self.send_event("answer_zh_token", {"content": chunk})
            answer_zh = "".join(answer_parts).strip()
            if not answer_zh:
                raise RuntimeError("神农没有返回中文回答。")
            shennong_complete = time.perf_counter() - shennong_started
            self.send_event("answer_zh_done", {"answer_zh": answer_zh})
            turn_id = (save_chinese_turn(owner, conversation_id, input_kind=input_kind,
                                        original_input=original_input, question_zh=public_question,
                                        answer_zh=answer_zh, observation=observation) if owner else None)
            self.send_event("translation_status", {"message": "中文回答已完成，正在翻译为维吾尔语…"})
        except (RuntimeError, OSError) as exc:
            try:
                self.send_event("error", {"error": str(exc) or "神农回答失败。", "stage": "shennong"})
            except OSError:
                pass
            return
        translation_started = time.perf_counter()
        try:
            answer_ug = translate_chinese_to_uyghur(
                answer_zh, _translation_terms_for_answer(answer_zh, terminology),
                api_key=_key("TENCENT_TOKENHUB_API_KEY"))
            zh_ug_seconds = time.perf_counter() - translation_started
            total = time.perf_counter() - started
            _log("双语流式问答", shennong_first_token=first_token_seconds or shennong_complete,
                 shennong_complete=shennong_complete, zh_to_ug=zh_ug_seconds, total=total)
            if turn_id: finish_translation(owner, turn_id, answer_ug)
            self.send_event("done", {
                "question_zh": public_question, "answer_zh": answer_zh, "answer_ug": answer_ug,
                "conversation_id": conversation_id,
                "timings": {"shennong_first_token": round(first_token_seconds or shennong_complete, 2),
                            "shennong_complete": round(shennong_complete, 2),
                            "zh_to_ug": round(zh_ug_seconds, 2), "total": round(total, 2)},
            })
        except TranslationError as exc:
            if turn_id: finish_translation(owner, turn_id, failed=True)
            _log("双语流式问答-回译失败", shennong_first_token=first_token_seconds or shennong_complete,
                 shennong_complete=shennong_complete, zh_to_ug=time.perf_counter() - translation_started,
                 total=time.perf_counter() - started)
            try:
                self.send_event("translation_error", {
                    "error": f"中文回答已保留，但腾讯中转维失败：{exc}",
                    "stage": "tencent_zh_to_ug", "answer_zh": answer_zh})
            except OSError:
                pass

    def handle_chinese_text(self, payload: object, *, stream: bool) -> None:
        started = time.perf_counter()
        question = payload.get("question") if isinstance(payload, dict) else None
        if not isinstance(question, str) or not question.strip():
            self.send_json(400, {"error": "请先输入中文问题。", "stage": "request"})
            return
        question = question.strip()
        if len(question) > MAX_QUESTION_CHARS:
            self.send_json(413, {"error": "问题不能超过 2000 字。", "stage": "request"})
            return
        try: conversation_id = self.conversation_id(payload)
        except ValueError: return
        if not self.require_keys(): return
        terms = terminology_for_chinese_text(question)
        input_kind = "chinese_voice" if isinstance(payload, dict) and payload.get("input_kind") == "chinese_voice" else "text"
        if stream:
            self._stream_answer(question, terms, started=started, conversation_id=conversation_id,
                                original_input=question, input_kind=input_kind)
        else:
            try: self.send_json(200, self._sync_answer(question, terms, started=started,
                                 conversation_id=conversation_id, original_input=question, input_kind=input_kind))
            except RuntimeError as exc: self.send_json(502, {"error": str(exc), "stage": "shennong_or_translation"})

    def handle_uyghur_text(self, payload: object, *, stream: bool) -> None:
        started = time.perf_counter()
        question = payload.get("question") if isinstance(payload, dict) else None
        if not isinstance(question, str) or not question.strip():
            self.send_json(400, {"error": "请先输入维吾尔语问题。", "stage": "request"})
            return
        if len(question) > MAX_QUESTION_CHARS:
            self.send_json(413, {"error": "维语问题不能超过 2000 字。", "stage": "request"})
            return
        try: conversation_id = self.conversation_id(payload)
        except ValueError: return
        if not self.require_keys(): return
        correction_started = time.perf_counter()
        corrected = correct_arabic_text(question)
        correction_seconds = time.perf_counter() - correction_started
        if not corrected["glossary_loaded"]:
            self.send_json(503, {"error": "维语农牧词汇表未加载。", "stage": "glossary"})
            return
        terms = terminology_from_corrections(corrected["corrections"])
        translate_started = time.perf_counter()
        try:
            question_zh = translate_uyghur_to_chinese(
                corrected["transcription_arabic"], terms, api_key=_key("TENCENT_TOKENHUB_API_KEY"))
        except TranslationError as exc:
            self.send_json(502, {"error": f"腾讯维转中失败：{exc}", "stage": "tencent_ug_to_zh"})
            return
        ug_zh_seconds = time.perf_counter() - translate_started
        _log("维文文字前处理", glossary=correction_seconds, ug_to_zh=ug_zh_seconds)
        info = {"question_info": {"transcription_raw": question.strip(),
                "transcription": corrected["transcription_arabic"], "corrections": corrected["corrections"],
                "question_zh": question_zh,
                "timings": {"glossary": round(correction_seconds, 2), "ug_to_zh": round(ug_zh_seconds, 2)}}}
        if stream:
            self._stream_answer(question_zh, terms, started=started, extra=info,
                                conversation_id=conversation_id, original_input=question,
                                input_kind="uyghur_text")
        else:
            try: self.send_json(200, self._sync_answer(question_zh, terms, started=started, extra=info["question_info"],
                                 conversation_id=conversation_id, original_input=question, input_kind="uyghur_text"))
            except RuntimeError as exc: self.send_json(502, {"error": str(exc), "stage": "shennong_or_translation", "question_zh": question_zh})

    def _decode_audio(self, payload: object) -> bytes | None:
        data_url = payload.get("audio") if isinstance(payload, dict) else None
        if not isinstance(data_url, str) or "," not in data_url:
            self.send_json(400, {"error": "请先录制维语语音。", "stage": "asr"}); return None
        prefix, encoded = data_url.split(",", 1)
        mime = prefix.removeprefix("data:").removesuffix(";base64")
        if prefix != f"data:{mime};base64" or mime not in AUDIO_SIGNATURES:
            self.send_json(415, {"error": "浏览器录音格式不受支持。", "stage": "asr"}); return None
        try: audio = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            self.send_json(400, {"error": "音频内容无法读取。", "stage": "asr"}); return None
        sig = {"mp3": audio.startswith(b"ID3") or (len(audio)>1 and audio[0]==0xff and audio[1]&0xe0==0xe0),
               "wav": audio.startswith(b"RIFF") and audio[8:12]==b"WAVE",
               "webm": audio.startswith(b"\x1aE\xdf\xa3"), "ogg": audio.startswith(b"OggS"),
               "mp4": len(audio)>=12 and audio[4:8]==b"ftyp"}
        if not any(sig[kind] for kind in AUDIO_SIGNATURES[mime]):
            self.send_json(415, {"error": "文件内容与音频格式不符。", "stage": "asr"}); return None
        if len(audio) > MAX_AUDIO_BYTES:
            self.send_json(413, {"error": "音频不能超过 8 MB。", "stage": "asr"}); return None
        return audio

    def handle_uyghur_audio(self, payload: object, *, stream: bool) -> None:
        started = time.perf_counter()
        try: conversation_id = self.conversation_id(payload)
        except ValueError: return
        audio = self._decode_audio(payload)
        if audio is None or not self.require_keys(): return
        try:
            asr_started = time.perf_counter(); latin, inference_seconds = recognize_audio(audio)
            asr_seconds = time.perf_counter() - asr_started
        except RuntimeError as exc:
            self.send_json(503, {"error": f"维语语音识别失败：{exc}", "stage": "asr"}); return
        raw_arabic = latin_to_uyghur_arabic(latin)
        correction_started = time.perf_counter(); corrected = correct_transcription(latin)
        correction_seconds = time.perf_counter() - correction_started
        if not corrected["glossary_loaded"]:
            self.send_json(503, {"error": "维语农牧词汇表未加载。", "stage": "glossary"}); return
        corrected_arabic = corrected["transcription_arabic"] or raw_arabic
        terms = terminology_from_corrections(corrected["corrections"])
        translate_started = time.perf_counter()
        try:
            question_zh = translate_uyghur_to_chinese(corrected_arabic, terms, api_key=_key("TENCENT_TOKENHUB_API_KEY"))
        except TranslationError as exc:
            self.send_json(502, {"error": f"腾讯维转中失败：{exc}", "stage": "tencent_ug_to_zh",
                           "transcription_raw": raw_arabic, "transcription": corrected_arabic,
                           "corrections": corrected["corrections"]}); return
        ug_zh_seconds = time.perf_counter() - translate_started
        _log("维语语音前处理", asr=asr_seconds, glossary=correction_seconds, ug_to_zh=ug_zh_seconds)
        transcript = {"transcription_raw": raw_arabic, "transcription": corrected_arabic,
                      "transcription_latin": latin, "corrections": corrected["corrections"],
                      "glossary_loaded": True, "question_zh": question_zh,
                      "inference_seconds": round(inference_seconds, 2),
                      "timings": {"asr": round(asr_seconds,2), "glossary": round(correction_seconds,2),
                                  "ug_to_zh": round(ug_zh_seconds,2)}}
        if stream:
            self._stream_answer(question_zh, terms, started=started, extra={"transcript": transcript},
                                conversation_id=conversation_id, original_input=raw_arabic,
                                input_kind="uyghur_voice")
        else:
            try: self.send_json(200, self._sync_answer(question_zh, terms, started=started, extra=transcript,
                                 conversation_id=conversation_id, original_input=raw_arabic,
                                 input_kind="uyghur_voice"))
            except RuntimeError as exc: self.send_json(502, {"error": str(exc), "stage": "shennong_or_translation", **transcript})

    def _decode_image(self, payload: object) -> tuple[bytes, str, str] | None:
        if not isinstance(payload, dict):
            self.send_json(400, {"error": "图片请求格式不正确。", "stage": "vision"}); return None
        question, data_url = payload.get("question", ""), payload.get("image")
        if not isinstance(question, str) or len(question) > MAX_IMAGE_QUESTION_CHARS:
            self.send_json(400, {"error": "补充问题不能超过 500 字。", "stage": "vision"}); return None
        if not isinstance(data_url, str) or "," not in data_url:
            self.send_json(400, {"error": "请先上传 JPG 或 PNG 照片。", "stage": "vision"}); return None
        prefix, encoded = data_url.split(",", 1); mime = prefix.removeprefix("data:").removesuffix(";base64")
        if prefix != f"data:{mime};base64" or mime not in IMAGE_TYPES:
            self.send_json(415, {"error": "目前只支持 JPG 和 PNG 照片。", "stage": "vision"}); return None
        try: image = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            self.send_json(400, {"error": "照片内容无法读取。", "stage": "vision"}); return None
        if not image.startswith(IMAGE_TYPES[mime]) or len(image) > MAX_IMAGE_BYTES:
            self.send_json(415, {"error": "照片格式不符或超过 4 MB。", "stage": "vision"}); return None
        return image, mime, question.strip()

    def handle_image(self, payload: object, *, stream: bool) -> None:
        try: conversation_id = self.conversation_id(payload)
        except ValueError: return
        started = time.perf_counter(); decoded = self._decode_image(payload)
        if decoded is None or not self.require_keys(): return
        image, mime, question = decoded
        try:
            vision_started = time.perf_counter()
            observation = inspect_agricultural_image(image, mime, _key("SHENNONG_API_KEY")).strip()
            vision_seconds = time.perf_counter() - vision_started
        except RuntimeError as exc:
            self.send_json(502, {"error": f"图片识别失败：{exc}", "stage": "vision"}); return
        if not observation or observation.startswith(("非农牧业图片：", "无法辨认：")):
            self.send_json(422, {"observation": observation or "无法辨认：未返回观察结果。",
                           "error": "请上传清晰的农作物或牲畜照片。", "stage": "vision"}); return
        question_zh, terms = question, []
        if question and ARABIC_TEXT_RE.search(question):
            corrected = correct_arabic_text(question)
            if not corrected["glossary_loaded"]:
                self.send_json(503, {"error": "维语农牧词汇表未加载。", "stage": "glossary"}); return
            terms = terminology_from_corrections(corrected["corrections"])
            try:
                question_zh = translate_uyghur_to_chinese(corrected["transcription_arabic"], terms,
                                                          api_key=_key("TENCENT_TOKENHUB_API_KEY"))
            except TranslationError as exc:
                self.send_json(502, {"error": f"腾讯维转中失败：{exc}", "stage": "tencent_ug_to_zh",
                               "observation": observation}); return
        if not question_zh:
            question_zh = "请根据图片中可见情况，说明应该先检查什么、如何处理，以及哪些情况需要找农技人员或兽医。"
        prompt = ("以下是视觉模型对农牧业照片的客观观察，不是确诊：\n" + observation +
                  "\n\n用户的中文问题：" + question_zh +
                  "\n请基于可见事实回答，不确定的病因要说明不确定，不得编造图片外症状。")
        terms = _translation_terms_for_answer(observation + question_zh, terms)
        _log("图片前处理", vision=vision_seconds)
        if stream:
            self._stream_answer(prompt, terms, started=started,
                                extra={"observation": {"observation": observation, "question_zh": question_zh}},
                                display_question_zh=question_zh, conversation_id=conversation_id,
                                original_input=question or "[仅图片]", input_kind="image",
                                observation=observation)
        else:
            try:
                result = self._sync_answer(prompt, terms, started=started, extra={"observation": observation},
                                           display_question_zh=question_zh, conversation_id=conversation_id,
                                           original_input=question or "[仅图片]", input_kind="image",
                                           observation=observation)
                result["question_zh"] = question_zh; self.send_json(200, result)
            except RuntimeError as exc:
                self.send_json(502, {"error": str(exc), "stage": "shennong_or_translation", "observation": observation})

    def handle_uyghur_synthesis(self, payload: object) -> None:
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str) or not text.strip():
            self.send_json(400, {"error": "没有可朗读的维文内容。", "stage": "uyghur_tts"}); return
        if len(text.encode("utf-8")) >= 8000:
            self.send_json(413, {"error": "维文回答太长，暂时无法一次朗读。", "stage": "uyghur_tts"}); return
        try: audio = synthesize_uyghur(text)
        except TTSFailure as exc:
            self.send_json(502, {"error": f"维语语音合成失败：{exc}", "stage": "uyghur_tts"}); return
        self.send_response(200); self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(audio))); self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff"); self.end_headers(); self.wfile.write(audio)


def main() -> None:
    port = int(os.environ.get("PORT", os.environ.get("SHENNONG_PORT", "8765")))
    host = os.environ.get("SHENNONG_BIND_HOST", "127.0.0.1")
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise RuntimeError("免登录历史记录版只允许绑定本机地址 127.0.0.1。")
    public_origin = os.environ.get("SHENNONG_PUBLIC_ORIGIN", "").rstrip("/")
    if public_origin:
        parsed = urlsplit(public_origin)
        if parsed.scheme != "https" or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
            raise RuntimeError("SHENNONG_PUBLIC_ORIGIN 必须是 HTTPS 域名源地址，例如 https://example.com。")
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"神农网页已启动：http://{host}:{port}/", flush=True)
    print(f"服务版本：{BUILD_ID}（腾讯 hy-mt2-plus 独立翻译 + 神农中文回答）", flush=True)
    if not _key("SHENNONG_API_KEY"): print("未配置 SHENNONG_API_KEY。", flush=True)
    if not _key("TENCENT_TOKENHUB_API_KEY"): print("未配置 TENCENT_TOKENHUB_API_KEY；中维双语问答暂不可用。", flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__ == "__main__":
    main()
