"""Pipeline tests without paid network calls."""

import base64
import json
import os
import socket
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, call, patch
from urllib import error, request

from server import BUILD_ID, Handler, POST_PATHS, STATIC_FILES
from tencent_hymt import TranslationError


KEYS = {"SHENNONG_API_KEY": "shennong-test", "TENCENT_TOKENHUB_API_KEY": "tencent-test"}


class PipelineUnitTests(unittest.TestCase):
    def handler(self):
        handler = Handler.__new__(Handler)
        handler.send_json = Mock()
        handler.begin_event_stream = Mock()
        handler.send_event = Mock()
        return handler

    def test_typed_uyghur_is_translated_before_shennong(self):
        handler = self.handler()
        with patch.dict(os.environ, KEYS, clear=False), \
             patch("server.correct_arabic_text", return_value={"transcription_arabic": "قوي", "corrections": [], "glossary_loaded": True}), \
             patch("server.translate_uyghur_to_chinese", return_value="我的羊不吃草" ) as ug_zh, \
             patch.object(handler, "_sync_answer", return_value={"answer_zh": "答", "answer_ug": "جاۋاب"}) as answer:
            handler.handle_uyghur_text({"question": "قوي"}, stream=False)
        ug_zh.assert_called_once()
        self.assertEqual(answer.call_args.args[0], "我的羊不吃草")

    def test_chinese_voice_uses_existing_chinese_answer_path(self):
        handler = self.handler()
        with patch.object(handler, "conversation_id", return_value="owned-chat"), \
             patch.object(handler, "require_keys", return_value=True), \
             patch.object(handler, "_stream_answer") as answer:
            handler.handle_chinese_text({"question": "羊发烧了怎么办", "input_kind": "chinese_voice"}, stream=True)
        self.assertEqual(answer.call_args.args[0], "羊发烧了怎么办")
        self.assertEqual(answer.call_args.kwargs["input_kind"], "chinese_voice")
        self.assertEqual(answer.call_args.kwargs["conversation_id"], "owned-chat")

    def test_uyghur_voice_transcribes_and_translates_before_answer(self):
        handler = self.handler()
        with patch.object(handler, "conversation_id", return_value="owned-chat"), \
             patch.object(handler, "_decode_audio", return_value=b"mock"), \
             patch.object(handler, "require_keys", return_value=True), \
             patch("server.recognize_audio", return_value=("qoy", 0.1)), \
             patch("server.latin_to_uyghur_arabic", return_value="قوي"), \
             patch("server.correct_transcription", return_value={"transcription_arabic": "قوي", "corrections": [], "glossary_loaded": True}), \
             patch("server.translate_uyghur_to_chinese", return_value="我的羊怎么了？") as translate, \
             patch.object(handler, "_stream_answer") as answer:
            handler.handle_uyghur_audio({"audio": "mock"}, stream=True)
        translate.assert_called_once()
        self.assertEqual(answer.call_args.args[0], "我的羊怎么了？")
        self.assertEqual(answer.call_args.kwargs["input_kind"], "uyghur_voice")
        self.assertEqual(answer.call_args.kwargs["conversation_id"], "owned-chat")

    def test_ug_to_zh_failure_never_calls_shennong(self):
        handler = self.handler()
        with patch.dict(os.environ, KEYS, clear=False), \
             patch("server.correct_arabic_text", return_value={"transcription_arabic": "قوي", "corrections": [], "glossary_loaded": True}), \
             patch("server.translate_uyghur_to_chinese", side_effect=TranslationError("失败")), \
             patch.object(handler, "_sync_answer") as answer:
            handler.handle_uyghur_text({"question": "قوي"}, stream=False)
        answer.assert_not_called()
        self.assertEqual(handler.send_json.call_args.args[0], 502)
        self.assertEqual(handler.send_json.call_args.args[1]["stage"], "tencent_ug_to_zh")

    def test_stream_translates_only_after_chinese_answer_finishes(self):
        handler = self.handler()
        order = []
        def shennong(*_):
            order.append("shennong")
            yield "先检查"
            yield "饮水。"
        def translate(text, *_args, **_kwargs):
            order.append("translate")
            self.assertEqual(text, "先检查饮水。")
            return "سۇنى تەكشۈرۈڭ."
        with patch.dict(os.environ, KEYS, clear=False), \
             patch("server.stream_chinese_agricultural_answer", side_effect=shennong), \
             patch("server.translate_chinese_to_uyghur", side_effect=translate):
            handler._stream_answer("羊不吃草", [], started=0.0)
        self.assertEqual(order, ["shennong", "translate"])
        event_names = [item.args[0] for item in handler.send_event.call_args_list]
        self.assertLess(event_names.index("answer_zh_done"), event_names.index("done"))

    def test_zh_to_ug_failure_preserves_chinese_event(self):
        handler = self.handler()
        with patch.dict(os.environ, KEYS, clear=False), \
             patch("server.stream_chinese_agricultural_answer", return_value=iter(["中文回答"])), \
             patch("server.translate_chinese_to_uyghur", side_effect=TranslationError("配额不足")):
            handler._stream_answer("中文问题", [], started=0.0)
        events = {item.args[0]: item.args[1] for item in handler.send_event.call_args_list}
        self.assertEqual(events["answer_zh_done"]["answer_zh"], "中文回答")
        self.assertEqual(events["translation_error"]["answer_zh"], "中文回答")

    def test_glossary_hits_are_passed_to_tencent(self):
        handler = self.handler()
        corrections = [{"heard": "qoy", "standard": "قوي", "chinese": "羊"}]
        with patch.dict(os.environ, KEYS, clear=False), \
             patch("server.correct_arabic_text", return_value={"transcription_arabic": "قوي", "corrections": corrections, "glossary_loaded": True}), \
             patch("server.translate_uyghur_to_chinese", return_value="羊") as translate, \
             patch.object(handler, "_sync_answer", return_value={}):
            handler.handle_uyghur_text({"question": "قوي"}, stream=False)
        self.assertIn(("قوي", "羊"), translate.call_args.args[1])

    def test_image_pipeline_returns_bilingual_answer(self):
        handler = self.handler()
        image = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nmock").decode()
        with patch.dict(os.environ, KEYS, clear=False), \
             patch("server.inspect_agricultural_image", return_value="可见叶片有黄色斑点。"), \
             patch.object(handler, "_sync_answer", return_value={"answer_zh": "检查叶背", "answer_ug": "يوپۇرماقنى تەكشۈرۈڭ"}) as answer:
            handler.handle_image({"image": image, "question": "这是什么？"}, stream=False)
        self.assertIn("客观观察", answer.call_args.args[0])
        result = handler.send_json.call_args.args[1]
        self.assertEqual(result["answer_ug"], "يوپۇرماقنى تەكشۈرۈڭ")

    def test_missing_tencent_key_is_distinct(self):
        handler = self.handler()
        with patch.dict(os.environ, {"SHENNONG_API_KEY": "ok", "TENCENT_TOKENHUB_API_KEY": ""}, clear=False):
            self.assertFalse(handler.require_keys())
        self.assertEqual(handler.send_json.call_args.args[1]["stage"], "translation")


class LocalModeStaticTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]

    def test_homepage_starts_without_login_and_has_history_controls(self):
        page = (self.root / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<div class="page-shell">', page)
        for obsolete in ('id="auth-panel"', 'id="login-password"', 'id="logout-button"'):
            self.assertNotIn(obsolete, page)
        for restored in ('id="history-toggle"', 'id="new-conversation"', 'id="conversation-turns"'):
            self.assertIn(restored, page)
        self.assertIn(BUILD_ID, page)

    def test_local_routes_have_history_without_account_endpoints(self):
        self.assertIn("/api/conversations", POST_PATHS)
        self.assertFalse(any(path.startswith(("/api/auth", "/api/account")) for path in POST_PATHS))
        self.assertNotIn("/api/auth/me", STATIC_FILES)

    def test_frontend_uses_history_without_api_credentials(self):
        resources = (self.root / "web" / "index.html").read_text(encoding="utf-8") + \
                    (self.root / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("/api/conversations", resources)
        self.assertNotIn("/api/auth/", resources)
        for secret_marker in ("SHENNONG_API_KEY", "TENCENT_TOKENHUB_API_KEY", "XFYUN_TTS_API_SECRET"):
            self.assertNotIn(secret_marker, resources)


class HttpCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            with socket.create_connection(cls.server.server_address, timeout=1):
                pass
        except OSError as exc:
            if hasattr(cls, "server"):
                cls.server.server_close()
            raise unittest.SkipTest(f"Loopback sockets are unavailable in this runner: {exc}")
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(timeout=3)

    def test_page_assets_and_health(self):
        for path in ("/", "/static/styles.css", "/static/app.js", "/static/ui_locale.js", "/static/grassland.css", "/static/grassland-home.jpg"):
            with request.urlopen(self.url + path, timeout=3) as response:
                self.assertEqual(response.status, 200)
                if path == "/":
                    self.assertEqual(response.headers.get("Cache-Control"), "no-store")
                elif path.endswith((".css", ".js")):
                    self.assertEqual(response.headers.get("Cache-Control"), "no-cache")
        with request.urlopen(self.url + "/api/health", timeout=3) as response:
            result = json.load(response)
        self.assertEqual(result["build"], BUILD_ID)
        self.assertEqual(result["build"], "local-history-2026-10-20-1")
        self.assertEqual(result["tencent_model"], "hy-mt2-plus")

    def test_other_origin_is_rejected(self):
        req = request.Request(self.url + "/api/ask", data=b'{"question":"test"}', method="POST",
                              headers={"Content-Type": "application/json", "Origin": "https://bad.example"})
        with self.assertRaises(error.HTTPError) as caught:
            request.urlopen(req, timeout=3)
        self.assertEqual(caught.exception.code, 403)

    def test_local_page_has_no_login_and_has_history_api(self):
        with request.urlopen(self.url + "/", timeout=3) as response:
            page = response.read().decode("utf-8")
        self.assertIn('<div class="page-shell">', page)
        self.assertNotIn('id="login-password"', page)
        self.assertNotIn('id="auth-panel"', page)
        self.assertIn('<nav class="history-nav" aria-label="对话管理">', page)
        with self.assertRaises(error.HTTPError) as caught:
            request.urlopen(self.url + "/api/auth/me", timeout=3)
        self.assertEqual(caught.exception.code, 404)
        with request.urlopen(self.url + "/api/conversations", timeout=3) as response:
            self.assertIn("conversations", json.load(response))
        req = request.Request(self.url + "/api/ask", data=b'{"question":""}', method="POST",
                              headers={"Content-Type": "application/json", "Origin": self.url})
        with self.assertRaises(error.HTTPError) as caught:
            request.urlopen(req, timeout=3)
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(json.load(caught.exception), {"error": "请先输入中文问题。", "stage": "request"})

    def test_create_open_and_delete_history_without_login(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp, \
             patch.dict(os.environ, {"SHENNONG_CONVERSATIONS_DB": str(Path(tmp) / "history.sqlite3")}):
            create = request.Request(self.url + "/api/conversations", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json", "Origin": self.url})
            with request.urlopen(create, timeout=3) as response:
                self.assertEqual(response.status, 201)
                conversation_id = json.load(response)["id"]
            with request.urlopen(self.url + "/api/conversations/" + conversation_id, timeout=3) as response:
                self.assertEqual(json.load(response)["turns"], [])
            delete = request.Request(self.url + "/api/conversations/" + conversation_id, method="DELETE",
                                     headers={"Origin": self.url})
            with request.urlopen(delete, timeout=3) as response:
                self.assertTrue(json.load(response)["deleted"])
            with self.assertRaises(error.HTTPError) as caught:
                request.urlopen(self.url + "/api/conversations/" + conversation_id, timeout=3)
            self.assertEqual(caught.exception.code, 404)

    def test_frontend_does_not_contain_secret_values(self):
        root = __import__("pathlib").Path(__file__).resolve().parents[1]
        resources = (root / "web" / "index.html").read_text(encoding="utf-8") + (root / "web" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("shennong-test", resources)
        self.assertNotIn("tencent-test", resources)
        self.assertNotIn("TENCENT_TOKENHUB_API_KEY", resources)


if __name__ == "__main__":
    unittest.main()
