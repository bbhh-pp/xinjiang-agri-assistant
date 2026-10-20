"""Minimal server-side client for iFlytek streaming TTS."""

import base64
import hashlib
import hmac
import json
import os
import socket
import ssl
import struct
import time
from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.parse import urlencode


HOST = "tts-api.xfyun.cn"
PATH = "/v2/tts"
VOICE = os.environ.get("XFYUN_TTS_VOICE", "x2_ugsp_dilare").strip()
MAX_AUDIO_BYTES = 16 * 1024 * 1024


class TTSFailure(RuntimeError):
    pass


def _auth_url(api_key: str, api_secret: str) -> str:
    date = format_datetime(datetime.now(timezone.utc), usegmt=True)
    signing_text = f"host: {HOST}\ndate: {date}\nGET {PATH} HTTP/1.1"
    signature = base64.b64encode(
        hmac.new(api_secret.encode(), signing_text.encode(), hashlib.sha256).digest()
    ).decode()
    authorization_origin = (
        f'api_key="{api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    query = urlencode({
        "authorization": base64.b64encode(authorization_origin.encode()).decode(),
        "date": date,
        "host": HOST,
    })
    return f"{PATH}?{query}"


def _send_frame(sock: ssl.SSLSocket, payload: bytes, opcode: int = 1) -> None:
    first = bytes([0x80 | opcode])
    mask = os.urandom(4)
    size = len(payload)
    if size < 126:
        header = first + bytes([0x80 | size])
    elif size < 65536:
        header = first + bytes([0x80 | 126]) + struct.pack("!H", size)
    else:
        header = first + bytes([0x80 | 127]) + struct.pack("!Q", size)
    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    sock.sendall(header + mask + masked)


def _read_exact(sock: ssl.SSLSocket, count: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < count:
        part = sock.recv(count - len(chunks))
        if not part:
            raise TTSFailure("讯飞连接提前关闭，请稍后重试。")
        chunks.extend(part)
    return bytes(chunks)


def _read_frame(sock: ssl.SSLSocket) -> tuple[bool, int, bytes]:
    first, second = _read_exact(sock, 2)
    final = bool(first & 0x80)
    opcode = first & 0x0F
    length = second & 0x7F
    if length == 126:
        length = struct.unpack("!H", _read_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _read_exact(sock, 8))[0]
    masked = bool(second & 0x80)
    mask = _read_exact(sock, 4) if masked else b""
    if length > MAX_AUDIO_BYTES:
        raise TTSFailure("讯飞返回的音频过大，请缩短回答后重试。")
    payload = _read_exact(sock, length)
    if masked:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return final, opcode, payload


def synthesize_uyghur(text: str) -> bytes:
    """Return synthesized MP3 bytes using the backend's iFlytek credentials."""
    app_id = os.environ.get("XFYUN_TTS_APP_ID", "").strip()
    api_key = os.environ.get("XFYUN_TTS_API_KEY", "").strip()
    api_secret = os.environ.get("XFYUN_TTS_API_SECRET", "").strip()
    if not all((app_id, api_key, api_secret)):
        raise TTSFailure("讯飞维语语音合成尚未配置。请运行 set-xfyun-tts-key.cmd 保存密钥后重启网页。")
    if not text.strip():
        raise TTSFailure("没有可朗读的维文内容。")
    text_bytes = text.encode("utf-8")
    if len(text_bytes) >= 8000:
        raise TTSFailure("维文回答太长，暂时无法一次朗读；请缩短回答后重试。")

    path_query = _auth_url(api_key, api_secret)
    key = base64.b64encode(os.urandom(16)).decode()
    request_bytes = (
        f"GET {path_query} HTTP/1.1\r\nHost: {HOST}\r\nUpgrade: websocket\r\n"
        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    ).encode("ascii")
    audio = bytearray()
    text_message = bytearray()
    deadline = time.monotonic() + 45
    raw = None
    try:
        raw = socket.create_connection((HOST, 443), timeout=10)
        sock = ssl.create_default_context().wrap_socket(raw, server_hostname=HOST)
        sock.settimeout(10)
        sock.sendall(request_bytes)
        response = bytearray()
        while not response.endswith(b"\r\n\r\n"):
            part = sock.recv(1)
            if not part or len(response) > 16_384:
                raise TTSFailure("讯飞连接握手失败，请检查网络和密钥配置。")
            response.extend(part)
        status_line = response.split(b"\r\n", 1)[0]
        if b" 101 " not in status_line:
            raise TTSFailure(f"讯飞连接鉴权失败（{status_line.decode('latin1', 'replace')}）。请核对密钥、发音人权限和系统时间。")

        request_payload = {
            "common": {"app_id": app_id},
            "business": {"aue": "lame", "sfl": 1, "tte": "UTF8", "vcn": VOICE,
                         "speed": 50, "volume": 60, "pitch": 50},
            "data": {"status": 2, "text": base64.b64encode(text_bytes).decode()},
        }
        _send_frame(sock, json.dumps(request_payload, ensure_ascii=False).encode("utf-8"))
        while time.monotonic() < deadline:
            final, opcode, payload = _read_frame(sock)
            if opcode == 8:
                break
            if opcode == 9:
                _send_frame(sock, payload, opcode=10)
                continue
            if opcode == 1:
                text_message.clear()
            elif opcode != 0:
                continue
            text_message.extend(payload)
            if len(text_message) > MAX_AUDIO_BYTES:
                raise TTSFailure("讯飞返回的数据过大，请稍后重试。")
            if not final:
                continue
            try:
                result = json.loads(text_message)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise TTSFailure("讯飞返回的数据无法读取。") from exc
            if result.get("code") != 0:
                raise TTSFailure(f"讯飞合成失败（{result.get('code')}）：{result.get('message', '未知错误')}")
            data = result.get("data") or {}
            chunk = data.get("audio")
            if chunk:
                try:
                    audio.extend(base64.b64decode(chunk, validate=True))
                except (ValueError, base64.binascii.Error) as exc:
                    raise TTSFailure("讯飞音频数据损坏，请重试。") from exc
            if len(audio) > MAX_AUDIO_BYTES:
                raise TTSFailure("讯飞返回的音频过大，请缩短回答后重试。")
            if data.get("status") == 2:
                break
        else:
            raise TTSFailure("讯飞语音合成等待超时，请重试。")
        if not audio:
            raise TTSFailure("讯飞没有返回语音，请检查维语发音人是否已开通。")
        return bytes(audio)
    except TTSFailure:
        raise
    except (OSError, ssl.SSLError, socket.timeout) as exc:
        raise TTSFailure("连接讯飞语音服务失败，请检查网络后重试。") from exc
    finally:
        if raw is not None:
            try:
                raw.close()
            except OSError:
                pass
