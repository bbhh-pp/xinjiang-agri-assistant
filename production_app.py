"""ASGI deployment adapter that preserves the existing HTTP API handlers.

Run with Uvicorn. The local Windows launcher continues to use server.py.
Streaming bodies are passed through a bounded queue so SSE is flushed as the
existing handler emits it and a disconnected browser stops further writes.
"""

from __future__ import annotations

import asyncio
import io
import json
import queue
import threading
from email.message import Message
from types import SimpleNamespace
from urllib.parse import parse_qs

from server import Handler


MAX_BODY_BYTES = 11 * 1024 * 1024
STREAM_PATHS = {
    "/api/ask-stream", "/api/ask-uyghur-text-stream",
    "/api/ask-image-stream", "/api/transcribe-uyghur-stream",
}
_DONE = object()


class _BodyPipe:
    def __init__(self, *, streaming: bool) -> None:
        self.streaming = streaming
        self.buffer = io.BytesIO()
        self.chunks: queue.Queue[bytes | object] = queue.Queue(maxsize=16)
        self.closed = False

    def write(self, data: bytes) -> int:
        if not self.streaming:
            return self.buffer.write(data)
        if self.closed:
            raise BrokenPipeError("client disconnected")
        chunk = bytes(data)
        while not self.closed:
            try:
                self.chunks.put(chunk, timeout=0.2)
                return len(chunk)
            except queue.Full:
                continue
        raise BrokenPipeError("client disconnected")

    def flush(self) -> None:
        # Queue writes are visible to the ASGI consumer immediately; this
        # method keeps BaseHTTPRequestHandler's SSE flush contract intact.
        return None

    def close(self) -> None:
        self.closed = True
        if self.streaming:
            try:
                self.chunks.put_nowait(_DONE)
            except queue.Full:
                pass


class _ASGIHandler(Handler):
    """Run the established route methods against ASGI request/response state."""

    def __init__(self, scope: dict, body: bytes, pipe: _BodyPipe) -> None:
        self.command = scope["method"]
        raw_path = scope.get("raw_path", scope["path"].encode("ascii", "ignore")).decode("ascii", "ignore")
        query = scope.get("query_string", b"").decode("ascii", "ignore")
        self.path = raw_path + ("?" + query if query else "")
        self.request_version = "HTTP/1.1"
        self.client_address = (scope.get("client", ("unknown", 0))[0], 0)
        self.server = SimpleNamespace(server_port=int(scope.get("server", (None, 8767))[1] or 8767))
        self.headers = Message()
        for key, value in scope.get("headers", []):
            self.headers.add_header(key.decode("latin-1"), value.decode("latin-1"))
        self.rfile = io.BytesIO(body)
        self.wfile = pipe
        self.pipe = pipe
        self.status = 200
        self.response_headers: list[tuple[str, str]] = []
        self.headers_ready = threading.Event()

    def send_response(self, code: int, message: str | None = None) -> None:
        self.status = code

    def send_header(self, keyword: str, value: str) -> None:
        self.response_headers.append((keyword, value))

    def end_headers(self) -> None:
        self.headers_ready.set()

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        content = (message or "请求失败").encode("utf-8", "replace")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def dispatch(self) -> None:
        if self.command == "GET":
            self.do_GET()
        elif self.command == "POST":
            self.do_POST()
        elif self.command == "DELETE":
            self.do_DELETE()
        else:
            self.send_error(405, "Method not allowed")

    def run(self) -> None:
        try:
            self.dispatch()
        except Exception:
            if not self.headers_ready.is_set():
                self.send_json(500, {"error": "服务内部错误。", "stage": "server"})
        finally:
            if self.pipe.streaming:
                self.pipe.close()


class ProductionApp:
    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "lifespan":
            while True:
                event = await receive()
                if event["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif event["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        elif scope["type"] == "http":
            await self._http(scope, receive, send)

    async def _http(self, scope, receive, send) -> None:
        content_length = 0
        for key, value in scope.get("headers", []):
            if key.lower() == b"content-length":
                try:
                    content_length = int(value)
                except ValueError:
                    content_length = 0
                break
        if content_length > MAX_BODY_BYTES:
            await self._reply(send, 413, '{"error":"请求内容过大。","stage":"request"}'.encode("utf-8"),
                              [(b"content-type", b"application/json; charset=utf-8")])
            return

        chunks = bytearray()
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            chunks.extend(event.get("body", b""))
            if len(chunks) > MAX_BODY_BYTES:
                await self._reply(send, 413, '{"error":"请求内容过大。","stage":"request"}'.encode("utf-8"),
                                  [(b"content-type", b"application/json; charset=utf-8")])
                return
            if not event.get("more_body", False):
                break

        path = scope.get("path", "/")
        streaming = scope["method"] == "POST" and path in STREAM_PATHS
        pipe = _BodyPipe(streaming=streaming)
        handler = _ASGIHandler(scope, bytes(chunks), pipe)
        task = asyncio.create_task(asyncio.to_thread(handler.run))

        if not streaming:
            try:
                await task
            except Exception:
                await self._reply(send, 500, '{"error":"服务内部错误。","stage":"server"}'.encode("utf-8"),
                                  [(b"content-type", b"application/json; charset=utf-8")])
                return
            headers = [(name.lower().encode("latin-1"), value.encode("latin-1"))
                       for name, value in handler.response_headers]
            body = pipe.buffer.getvalue()
            await self._reply(send, handler.status, body, headers)
            return

        ready = await asyncio.to_thread(handler.headers_ready.wait, 12)
        if not ready:
            pipe.close()
            await self._reply(send, 504, '{"error":"服务启动回应超时。","stage":"server"}'.encode("utf-8"),
                              [(b"content-type", b"application/json; charset=utf-8")])
            return
        headers = [(name.lower().encode("latin-1"), value.encode("latin-1"))
                   for name, value in handler.response_headers]
        await send({"type": "http.response.start", "status": handler.status, "headers": headers})

        disconnected = asyncio.Event()

        async def watch_disconnect():
            while True:
                event = await receive()
                if event["type"] == "http.disconnect":
                    disconnected.set()
                    pipe.close()
                    return

        watcher = asyncio.create_task(watch_disconnect())
        try:
            while True:
                if disconnected.is_set():
                    break
                try:
                    chunk = await asyncio.to_thread(pipe.chunks.get, True, 0.25)
                except queue.Empty:
                    if task.done():
                        break
                    continue
                if chunk is _DONE:
                    break
                await send({"type": "http.response.body", "body": chunk, "more_body": True})
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        except (OSError, asyncio.CancelledError):
            pipe.close()
            raise
        finally:
            pipe.close()
            watcher.cancel()

    @staticmethod
    async def _reply(send, status: int, body: bytes, headers: list[tuple[bytes, bytes]]) -> None:
        names = {name.lower() for name, _ in headers}
        if b"content-length" not in names:
            headers.append((b"content-length", str(len(body)).encode("ascii")))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body, "more_body": False})


app = ProductionApp()
