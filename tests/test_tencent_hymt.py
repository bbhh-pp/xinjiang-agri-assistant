"""Tencent TokenHub request, parsing and retry tests."""

import io
import json
import unittest
from unittest.mock import patch
from urllib import error

from tencent_hymt import TranslationError, translate_chinese_to_uyghur, translate_uyghur_to_chinese


def response(text):
    return io.BytesIO(json.dumps({
        "choices": [{"finish_reason": "stop", "message": {"content": text}}]
    }, ensure_ascii=False).encode())


class TencentTranslationTests(unittest.TestCase):
    def test_uyghur_to_chinese_official_payload(self):
        with patch("tencent_hymt.request.urlopen", return_value=response("我的羊不吃草")) as open_url:
            result = translate_uyghur_to_chinese("قوي", [("قوي", "羊")], api_key="secret")
        self.assertEqual(result, "我的羊不吃草")
        sent = json.loads(open_url.call_args.args[0].data)
        self.assertEqual((sent["model"], sent["source"], sent["target"]), ("hy-mt2-plus", "ug", "zh"))
        self.assertFalse(sent["stream"])
        self.assertIn("قوي = 羊", sent["context"])

    def test_chinese_to_uyghur_reverses_terminology(self):
        with patch("tencent_hymt.request.urlopen", return_value=response("قوي")) as open_url:
            translate_chinese_to_uyghur("羊", [("قوي", "羊")], api_key="secret")
        sent = json.loads(open_url.call_args.args[0].data)
        self.assertEqual((sent["source"], sent["target"]), ("zh", "ug"))
        self.assertIn("羊 = قوي", sent["context"])

    def test_glossary_id_is_only_sent_when_configured(self):
        with patch("tencent_hymt.request.urlopen", return_value=response("羊")) as open_url:
            translate_uyghur_to_chinese("قوي", api_key="secret", glossary_id="real-id")
        sent = json.loads(open_url.call_args.args[0].data)
        self.assertEqual(sent["glossary_ids"], ["real-id"])

    def test_authentication_error_is_not_retried(self):
        failure = error.HTTPError("url", 401, "unauthorized", {}, io.BytesIO(b'{"error":{"message":"bad key"}}'))
        with patch("tencent_hymt.request.urlopen", side_effect=failure) as open_url:
            with self.assertRaisesRegex(TranslationError, "HTTP 401"):
                translate_uyghur_to_chinese("قوي", api_key="secret")
        self.assertEqual(open_url.call_count, 1)

    def test_429_is_retried_once(self):
        failure = error.HTTPError("url", 429, "limited", {}, io.BytesIO(b'{}'))
        with patch("tencent_hymt.request.urlopen", side_effect=[failure, response("羊")]) as open_url, \
             patch("tencent_hymt.time.sleep"):
            self.assertEqual(translate_uyghur_to_chinese("قوي", api_key="secret"), "羊")
        self.assertEqual(open_url.call_count, 2)


if __name__ == "__main__":
    unittest.main()
