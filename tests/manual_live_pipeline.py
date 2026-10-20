"""Short paid live check. Loads keys from environment and never prints them."""

import os
import time

from ask_shennong import stream_chinese_agricultural_answer
from tencent_hymt import translate_chinese_to_uyghur, translate_uyghur_to_chinese


def main() -> None:
    shennong_key = os.environ.get("SHENNONG_API_KEY", "").strip()
    tencent_key = os.environ.get("TENCENT_TOKENHUB_API_KEY", "").strip()
    question_zh = "羊不吃草怎么办？"
    if tencent_key:
        started = time.perf_counter()
        translated = translate_uyghur_to_chinese("قويۇم ئوت يېمەيۋاتىدۇ، نېمە قىلىمەن؟", [("قوي", "羊")], api_key=tencent_key)
        print(f"TENCENT_UG_ZH_SECONDS={time.perf_counter() - started:.2f}")
        print(f"TENCENT_UG_ZH_RESULT={translated}")
        question_zh = translated
    else:
        print("TENCENT_LIVE=SKIPPED_NO_KEY")
    if not shennong_key:
        print("SHENNONG_LIVE=SKIPPED_NO_KEY")
        return
    started = time.perf_counter()
    first = None
    parts = []
    for chunk in stream_chinese_agricultural_answer(question_zh, shennong_key):
        if first is None:
            first = time.perf_counter() - started
        parts.append(chunk)
    answer = "".join(parts).strip()
    print(f"SHENNONG_FIRST_TOKEN_SECONDS={first or 0:.2f}")
    print(f"SHENNONG_COMPLETE_SECONDS={time.perf_counter() - started:.2f}")
    print(f"SHENNONG_CHINESE_ONLY={bool(answer) and not any('\u0600' <= c <= '\u06ff' for c in answer)}")
    if tencent_key and answer:
        started = time.perf_counter()
        translated_answer = translate_chinese_to_uyghur(answer, [("قوي", "羊")], api_key=tencent_key)
        print(f"TENCENT_ZH_UG_SECONDS={time.perf_counter() - started:.2f}")
        print(f"TENCENT_ZH_UG_RESULT={translated_answer[:160]}")


if __name__ == "__main__":
    main()
