"""Deployment adapter checks; no paid service calls or credentials needed."""

import json
import queue
import unittest
from unittest.mock import patch

from production_app import _ASGIHandler, _BodyPipe, _DONE


class ProductionAppTests(unittest.TestCase):
    def _dispatch(self, scope, body=b"", *, streaming=False):
        pipe = _BodyPipe(streaming=streaming)
        handler = _ASGIHandler(scope, body, pipe)
        handler.run()
        if streaming:
            output = bytearray()
            while True:
                try:
                    chunk = pipe.chunks.get_nowait()
                except queue.Empty:
                    break
                if chunk is _DONE:
                    break
                output.extend(chunk)
            return handler.status, handler.response_headers, bytes(output)
        return handler.status, handler.response_headers, pipe.buffer.getvalue()

    @staticmethod
    def _scope(method="GET", path="/api/health", headers=()):
        return {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": method, "scheme": "http", "path": path,
            "raw_path": path.encode(), "query_string": b"", "headers": list(headers),
            "client": ("127.0.0.1", 12345), "server": ("127.0.0.1", 8767),
        }

    def test_health_and_shared_static_page_are_served_by_production_handler(self):
        status, _, body = self._dispatch(self._scope())
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["service"], "shennong-local")
        status, headers, body = self._dispatch(self._scope(path="/"))
        self.assertEqual(status, 200)
        self.assertIn(("Cache-Control", "no-store"), headers)
        self.assertIn("农牧问题，有答案", body.decode("utf-8"))

    def test_stream_route_works_without_login_in_local_mode(self):
        body = json.dumps({"question": "羊不吃草怎么办？"}, ensure_ascii=False).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            (b"origin", b"http://127.0.0.1:8767"),
        ]
        with patch.dict("os.environ", {
                "SHENNONG_API_KEY": "",
                "TENCENT_TOKENHUB_API_KEY": "",
        }):
            status, response_headers, response_body = self._dispatch(
                self._scope("POST", "/api/ask-stream", headers), body, streaming=True)
        self.assertEqual(status, 503)  # No API secrets are injected during this local test.
        self.assertIn(("Content-Type", "application/json; charset=utf-8"), response_headers)
        self.assertIn("神农密钥未配置", response_body.decode())

    def test_stream_route_flushes_sse_events_through_production_pipe(self):
        body = json.dumps({"question": "羊不吃草怎么办？"}, ensure_ascii=False).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            (b"origin", b"https://farm.example"),
        ]
        handler = _ASGIHandler(self._scope("POST", "/api/ask-stream", headers), body,
                               _BodyPipe(streaming=True))
        handler._same_origin = lambda: True
        handler.require_keys = lambda: True
        with patch("server.stream_chinese_agricultural_answer", return_value=iter(["先检查饮水。"])), \
             patch("server.translate_chinese_to_uyghur", return_value="سۇنى تەكشۈرۈڭ"):
            handler.run()
        output = bytearray()
        while True:
            chunk = handler.pipe.chunks.get_nowait()
            if chunk is _DONE:
                break
            output.extend(chunk)
        self.assertEqual(handler.status, 200)
        self.assertIn(b"event: answer_zh_token", output)
        self.assertIn("先检查饮水。", output.decode("utf-8"))
        self.assertIn(b"event: done", output)


if __name__ == "__main__":
    unittest.main()
