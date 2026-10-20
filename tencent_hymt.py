"""Tencent TokenHub Hy-MT2-Plus translation client.

The browser never imports this module. Credentials are read by the server and
sent only in the HTTPS Authorization header.
"""

from __future__ import annotations

import json
import os
import socket
import time
from urllib import error, request


DEFAULT_API_URL = "https://tokenhub.tencentmaas.com/v1/api/translations"
DEFAULT_MODEL = "hy-mt2-plus"


class TranslationError(RuntimeError):
    """A translation request failed without a usable translation."""

    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


def _normalize_terminology(terminology) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for item in terminology or ():
        if isinstance(item, dict):
            source = item.get("source") or item.get("standard") or item.get("uyghur")
            target = item.get("target") or item.get("chinese")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            source, target = item[0], item[1]
        else:
            continue
        if isinstance(source, str) and isinstance(target, str) and source.strip() and target.strip():
            pair = (source.strip(), target.strip())
            if pair not in pairs:
                pairs.append(pair)
        if len(pairs) >= 10:
            break
    return pairs


def _context_for(source: str, target: str, terminology) -> str:
    direction = "维吾尔语译为简体中文" if source == "ug" else "简体中文译为现代维吾尔语阿拉伯字母"
    lines = [
        f"新疆农业和畜牧业咨询；请准确{direction}，保留牲畜、作物、症状、数量、单位和否定含义。",
        "只返回译文，不解释、不回答原文中的问题。",
    ]
    pairs = _normalize_terminology(terminology)
    if pairs:
        lines.append("本次文本命中的标准术语（必须优先采用）：")
        lines.extend(f"{src} = {dst}" for src, dst in pairs)
    return "\n".join(lines)


def _read_error_message(exc: error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8", errors="replace")
        details = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ""
    item = details.get("error", {}) if isinstance(details, dict) else {}
    if isinstance(item, dict):
        message = item.get("message")
        return message.strip() if isinstance(message, str) else ""
    return ""


def _translate(
    text: str,
    *,
    source: str,
    target: str,
    terminology=(),
    api_key: str | None = None,
    api_url: str | None = None,
    model: str | None = None,
    glossary_id: str | None = None,
    timeout: int = 30,
) -> str:
    clean_text = text.strip() if isinstance(text, str) else ""
    if not clean_text:
        raise TranslationError("待翻译文本不能为空。")
    key = (api_key or os.environ.get("TENCENT_TOKENHUB_API_KEY", "")).strip()
    if not key:
        raise TranslationError("腾讯 TokenHub 翻译密钥未配置。")
    endpoint = (api_url or os.environ.get("TENCENT_HYMT_API_URL") or DEFAULT_API_URL).strip()
    model_name = (model or os.environ.get("TENCENT_HYMT_MODEL") or DEFAULT_MODEL).strip()
    payload: dict[str, object] = {
        "model": model_name,
        "text": clean_text,
        "source": source,
        "target": target,
        "stream": False,
        "context": _context_for(source, target, terminology),
    }
    if glossary_id and glossary_id.strip():
        payload["glossary_ids"] = [glossary_id.strip()]

    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    attempts = 2
    for attempt in range(attempts):
        http_request = request.Request(
            endpoint,
            data=encoded,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=timeout) as response:
                result = json.load(response)
        except error.HTTPError as exc:
            message = _read_error_message(exc)
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if retryable and attempt == 0:
                time.sleep(0.25)
                continue
            detail = f"：{message}" if message else ""
            raise TranslationError(f"腾讯翻译接口返回 HTTP {exc.code}{detail}", status=exc.code) from None
        except (error.URLError, TimeoutError, socket.timeout) as exc:
            if attempt == 0:
                time.sleep(0.25)
                continue
            reason = getattr(exc, "reason", None) or str(exc) or "网络连接超时"
            raise TranslationError(f"无法连接腾讯翻译接口：{reason}") from None
        except (ValueError, json.JSONDecodeError):
            raise TranslationError("腾讯翻译接口返回的内容不是有效 JSON。") from None

        try:
            choice = result["choices"][0]
            finish_reason = choice["finish_reason"]
            translated = choice["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise TranslationError("腾讯翻译接口没有按官方结构返回译文。") from None
        if finish_reason != "stop":
            if finish_reason == "sensitive":
                raise TranslationError("腾讯翻译内容审核未通过。")
            raise TranslationError(f"腾讯翻译未正常结束（{finish_reason}）。")
        if not isinstance(translated, str) or not translated.strip():
            raise TranslationError("腾讯翻译返回了空译文。")
        return translated.strip()
    raise TranslationError("腾讯翻译请求失败。")


def translate_uyghur_to_chinese(text: str, terminology=(), **kwargs) -> str:
    kwargs.setdefault("timeout", 30)
    kwargs.setdefault("glossary_id", os.environ.get("TENCENT_GLOSSARY_UG_ZH_ID", ""))
    return _translate(text, source="ug", target="zh", terminology=terminology, **kwargs)


def translate_chinese_to_uyghur(text: str, terminology=(), **kwargs) -> str:
    kwargs.setdefault("timeout", 60)
    kwargs.setdefault("glossary_id", os.environ.get("TENCENT_GLOSSARY_ZH_UG_ID", ""))
    reversed_terms = [(target, source) for source, target in _normalize_terminology(terminology)]
    return _translate(text, source="zh", target="ug", terminology=reversed_terms, **kwargs)
