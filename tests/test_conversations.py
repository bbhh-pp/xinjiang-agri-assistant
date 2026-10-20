"""Conversation persistence and context tests without paid API calls."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ask_shennong import _chinese_agriculture_messages
from account_store import activate_initial_admin
from conversation_store import (create_conversation, delete_conversation, finish_translation,
                                get_conversation, recent_context, save_chinese_turn)
from server import Handler
from tencent_hymt import TranslationError


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.db_env = patch.dict(os.environ, {"SHENNONG_CONVERSATIONS_DB": str(Path(self.tmp.name) / "history.sqlite3"),
                                            "SHENNONG_API_KEY": "test", "TENCENT_TOKENHUB_API_KEY": "test"})
        self.db_env.start()
        self.user_id = activate_initial_admin("long-test-password-123")["id"]

    def tearDown(self):
        self.db_env.stop()
        self.tmp.cleanup()

    def handler(self):
        handler = Handler.__new__(Handler)
        handler.begin_event_stream = Mock()
        handler.send_event = Mock()
        handler.send_json = Mock()
        handler.user_id = self.user_id
        return handler

    def test_followup_receives_previous_chinese_turn_but_other_chat_does_not(self):
        first = create_conversation(self.user_id)["id"]
        second = create_conversation(self.user_id)["id"]
        handler = self.handler()
        with patch("server.stream_chinese_agricultural_answer", return_value=iter(["先检查饮水。"])) as shennong, \
             patch("server.translate_chinese_to_uyghur", return_value="سۇنى تەكشۈرۈڭ"):
            handler._stream_answer("我的羊不吃食怎么办？", started=0, conversation_id=first,
                                   original_input="我的羊不吃食怎么办？")
        self.assertEqual(shennong.call_args.args[0], "我的羊不吃食怎么办？")
        self.assertEqual(recent_context(self.user_id, second), [])
        handler = self.handler()
        with patch("server.stream_chinese_agricultural_answer", return_value=iter(["请立即请兽医检查。"])) as shennong, \
             patch("server.translate_chinese_to_uyghur", return_value="دوختۇرغا بېرىڭ"):
            handler._stream_answer("它还腹胀，接下来怎么办？", started=0, conversation_id=first,
                                   original_input="它还腹胀，接下来怎么办？")
        history = shennong.call_args.kwargs["history"]
        self.assertEqual(history, [("我的羊不吃食怎么办？", "先检查饮水。")])
        messages = _chinese_agriculture_messages("它还腹胀，接下来怎么办？", history)
        self.assertEqual([part["role"] for part in messages[1:]], ["user", "assistant", "user"])
        self.assertEqual(len(get_conversation(self.user_id, first)["turns"]), 2)
        self.assertEqual(get_conversation(self.user_id, second)["turns"], [])

    def test_reload_translation_failure_and_image_observation(self):
        conversation = create_conversation(self.user_id)["id"]
        handler = self.handler()
        with patch("server.stream_chinese_agricultural_answer", return_value=iter(["观察叶背。"])), \
             patch("server.translate_chinese_to_uyghur", side_effect=TranslationError("失败")):
            handler._stream_answer("图片观察和问题", started=0, conversation_id=conversation,
                                   display_question_zh="叶子怎么了？", original_input="叶子怎么了？",
                                   input_kind="image", observation="可见黄色斑点。")
        saved = get_conversation(self.user_id, conversation)["turns"][0]
        self.assertEqual(saved["answer_zh"], "观察叶背。")
        self.assertEqual(saved["translation_status"], "failed")
        self.assertIn("照片观察：可见黄色斑点。", recent_context(self.user_id, conversation)[0][0])
        self.assertEqual(saved["answer_ug"], "")
        finish_translation(self.user_id, saved["id"], "يوپۇرماقنى كۆرۈڭ")
        self.assertEqual(get_conversation(self.user_id, conversation)["turns"][0]["translation_status"], "complete")
        self.assertTrue(delete_conversation(self.user_id, conversation))
        self.assertIsNone(get_conversation(self.user_id, conversation))

    def test_interrupted_stream_is_not_saved(self):
        conversation = create_conversation(self.user_id)["id"]
        handler = self.handler()
        handler.send_event.side_effect = lambda name, _data: (_ for _ in ()).throw(OSError("disconnected")) if name == "answer_zh_token" else None
        with patch("server.stream_chinese_agricultural_answer", return_value=iter(["半句话"])), \
             patch("server.translate_chinese_to_uyghur") as translate:
            handler._stream_answer("问题", started=0, conversation_id=conversation, original_input="问题")
        translate.assert_not_called()
        self.assertEqual(get_conversation(self.user_id, conversation)["turns"], [])

    def test_context_budget_does_not_cut_turns(self):
        conversation = create_conversation(self.user_id)["id"]
        for n in range(4):
            save_chinese_turn(self.user_id, conversation, input_kind="text", original_input=f"q{n}",
                              question_zh=f"q{n}", answer_zh="答" * 10)
        context = recent_context(self.user_id, conversation, max_turns=5, max_chars=20)
        self.assertEqual(context, [("q3", "答" * 10)])

    def test_uyghur_followup_translates_before_chinese_context(self):
        conversation = create_conversation(self.user_id)["id"]
        save_chinese_turn(self.user_id, conversation, input_kind="text", original_input="羊不吃草",
                          question_zh="我的羊不吃草怎么办？", answer_zh="先观察饮水。")
        handler = self.handler()
        with patch("server.correct_arabic_text", return_value={"transcription_arabic": "قوي", "corrections": [], "glossary_loaded": True}), \
             patch("server.translate_uyghur_to_chinese", return_value="它还腹胀怎么办？") as translate, \
             patch.object(handler, "_stream_answer") as answer:
            handler.handle_uyghur_text({"question": "قوي", "conversation_id": conversation}, stream=True)
        translate.assert_called_once()
        self.assertEqual(answer.call_args.args[0], "它还腹胀怎么办？")
        self.assertEqual(answer.call_args.kwargs["conversation_id"], conversation)
        self.assertEqual(recent_context(self.user_id, conversation), [("我的羊不吃草怎么办？", "先观察饮水。")])


if __name__ == "__main__":
    unittest.main()
