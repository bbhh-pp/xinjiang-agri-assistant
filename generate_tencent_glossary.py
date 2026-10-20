"""Generate reviewed Tencent glossary payloads from the corrected local TSV."""

from __future__ import annotations

import json
from pathlib import Path

from uyghur_agri_lexicon import GLOSSARY


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "tencent-glossary"


def unique_pairs() -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for item in GLOSSARY:
        pair = (item.uyghur_arabic.strip(), item.chinese.strip())
        if pair[0] and pair[1] and pair not in result:
            result.append(pair)
    return result


def write_direction(name: str, pairs: list[tuple[str, str]]) -> None:
    folder = OUTPUT / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "terms.tsv").write_text(
        "SourceTerm\tTargetTerm\n" + "\n".join(f"{source}\t{target}" for source, target in pairs) + "\n",
        encoding="utf-8-sig",
    )
    for batch_number, start in enumerate(range(0, len(pairs), 100), 1):
        payload = {
            "GlossaryId": "在腾讯控制台创建术语库后填写真实ID",
            "Entries": [
                {"SourceTerm": source, "TargetTerm": target}
                for source, target in pairs[start:start + 100]
            ],
        }
        (folder / f"create-entries-{batch_number:02d}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def main() -> None:
    pairs = unique_pairs()
    write_direction("ug-zh", pairs)
    write_direction("zh-ug", [(target, source) for source, target in pairs])
    print(f"已生成 {len(pairs)} 个双向术语对：{OUTPUT}")


if __name__ == "__main__":
    main()
