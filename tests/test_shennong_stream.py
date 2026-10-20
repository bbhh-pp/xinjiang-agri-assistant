"""Tests for the Shennong OpenAI-compatible SSE stream parser."""

import io
import json
import unittest
from unittest.mock import patch

from ask_shennong import _stream_chat_content, stream_chinese_agricultural_answer


class ShennongStreamTests(unittest.TestCase):
    def test_stream_request_reads_content_deltas_until_done(self):
        body = (
            b"data: {\"choices\":[{\"delta\":{\"content\":\"\\u4f60\"}}]}\n\n"
            b"data: {\"choices\":[{\"delta\":{\"content\":\"\\u597d\"}}]}\n\n"
            b"data: [DONE]\n\n"
        )
        with patch("ask_shennong.request.urlopen", return_value=io.BytesIO(body)) as open_url:
            chunks = list(_stream_chat_content([{"role": "user", "content": "test"}], "fake-key"))
        self.assertEqual(chunks, ["你", "好"])
        sent_request = open_url.call_args.args[0]
        payload = json.loads(sent_request.data.decode("utf-8"))
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["model"], "sn")

    def test_shennong_prompt_is_chinese_only_and_requests_chinese_only(self):
        with patch("ask_shennong._stream_chat_content", return_value=iter(["先检查饮水。"])) as stream:
            self.assertEqual(list(stream_chinese_agricultural_answer("羊不吃草怎么办？", "key")), ["先检查饮水。"])
        messages = stream.call_args.args[0]
        self.assertEqual(messages[1]["content"], "羊不吃草怎么办？")
        self.assertIn("只用简体中文回答", messages[0]["content"])
        self.assertNotIn("answer_ug", messages[0]["content"])


if __name__ == "__main__":
    unittest.main()
