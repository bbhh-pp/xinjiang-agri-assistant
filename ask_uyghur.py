"""维吾尔语文字提问：先翻译成中文，再交给神农回答。"""

import getpass
import os
import sys

from ask_shennong import ask_shennong
from tencent_hymt import translate_chinese_to_uyghur, translate_uyghur_to_chinese
from uyghur_agri_lexicon import correct_arabic_text, terminology_for_chinese_text, terminology_from_corrections


def main() -> int:
    try:
        question = input("请输入维吾尔语问题：").strip()
        if not question:
            print("问题不能为空。")
            return 1

        translation_key = os.environ.get("TENCENT_TOKENHUB_API_KEY", "").strip()
        if not translation_key:
            translation_key = getpass.getpass("请输入腾讯 TokenHub API Key（输入时不显示）：").strip()
        shennong_key = os.environ.get("SHENNONG_API_KEY", "").strip()
        if not shennong_key:
            shennong_key = getpass.getpass("请输入神农 API Key（输入时不显示）：").strip()
        if not translation_key or not shennong_key:
            print("缺少 API Key。")
            return 1

        corrected = correct_arabic_text(question)
        if not corrected["glossary_loaded"]:
            raise RuntimeError("维语农牧词汇表未加载。")
        terminology = terminology_from_corrections(corrected["corrections"])
        print("正在用腾讯 hy-mt2-plus 翻译维吾尔语问题……")
        chinese_question = translate_uyghur_to_chinese(
            corrected["transcription_arabic"], terminology, api_key=translation_key
        )
        print(f"中文问题：{chinese_question}")

        print("正在等待神农回答……")
        answer = ask_shennong(chinese_question, shennong_key)
        print("正在把中文回答翻译为维吾尔语……")
        answer_uyghur = translate_chinese_to_uyghur(
            answer, terminology + terminology_for_chinese_text(answer), api_key=translation_key
        )
        print(f"\n神农中文回答：\n{answer}\n\n腾讯维文翻译：\n{answer_uyghur}")
        return 0
    except (KeyboardInterrupt, EOFError):
        print("\n已取消。")
        return 1
    except RuntimeError as exc:
        print(f"调用失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
