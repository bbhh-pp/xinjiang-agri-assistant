"""Conservatively correct ASR terms using the supplied Uyghur agriculture glossary."""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
GLOSSARY_PATH = ROOT / "维文标准对照表_更正版.txt"
ARABIC_RE = re.compile(r"[\u0600-\u06ff\u0750-\u077f]+(?:[\s-]+[\u0600-\u06ff\u0750-\u077f]+)*")
HAN_RE = re.compile(r"[\u3400-\u9fff]")
LATIN_WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿƏə]+(?:['’][A-Za-zÀ-ÖØ-öø-ÿƏə]+)*")
ARABIC_DIACRITICS_RE = re.compile(r"[\u064b-\u065f\u0670\u0640]")
ARABIC_TO_LATIN = {
    "ا": "a", "ب": "b", "چ": "ch", "غ": "gh", "ش": "sh", "ژ": "zh",
    "ڭ": "ng", "د": "d", "ە": "e", "ف": "f", "گ": "g", "ھ": "h",
    "ى": "i", "ي": "y", "ج": "j", "ك": "k", "ل": "l", "م": "m",
    "ن": "n", "و": "o", "پ": "p", "ق": "q", "ر": "r", "س": "s",
    "ت": "t", "ۇ": "u", "ئ": "", "ۋ": "w", "خ": "x", "ز": "z",
    "ې": "é", "ۆ": "ö", "ۈ": "ü", "ى": "i", "ي": "y",
}


@dataclass(frozen=True)
class GlossaryEntry:
    chinese: str
    uyghur_arabic: str
    latin_aliases: tuple[str, ...]


def _normalize_arabic(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = ARABIC_DIACRITICS_RE.sub("", text)
    return text.translate(str.maketrans({"ى": "ي", "ی": "ي", "ک": "ك"}))


def _normalize_latin(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).casefold()
    return "".join(char for char in text if not unicodedata.combining(char) and char.isalnum())


def _arabic_as_latin(text: str) -> str:
    return "".join(ARABIC_TO_LATIN.get(char, char if char.isspace() else "") for char in text)


def _clean_chinese_name(text_before_arabic: str) -> str:
    fields = [re.sub(r"\s+", " ", field).strip(" ：:;；,，") for field in text_before_arabic.split("\t")]
    for field in reversed(fields):
        chinese = "".join(HAN_RE.findall(field))
        if chinese:
            return chinese
    return ""


def _latin_aliases(fields: list[str]) -> tuple[str, ...]:
    # The source is a hand-edited TSV and some rows have shifted columns. Read
    # romanization from the first post-Uyghur field that actually contains it.
    for field in fields:
        cleaned = ARABIC_RE.sub(" ", field)
        cleaned = HAN_RE.sub(" ", cleaned)
        words = [word.strip("'’-") for word in LATIN_WORD_RE.findall(cleaned)]
        words = [word for word in words if len(_normalize_latin(word)) >= 2]
        if words:
            return (" ".join(words),)
    return ()


def load_glossary(path: Path = GLOSSARY_PATH) -> tuple[GlossaryEntry, ...]:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return ()

    entries: list[GlossaryEntry] = []
    for line in lines:
        columns = line.split("\t")
        if len(columns) < 3 or not re.match(r"^[A-Z]{2}\d{3,}", columns[0].strip()):
            continue
        tail = "\t".join(columns[2:])
        arabic_match = ARABIC_RE.search(tail)
        if not arabic_match:
            continue
        chinese = _clean_chinese_name(tail[:arabic_match.start()])
        arabic = re.sub(r"\s+", " ", arabic_match.group()).strip(" -")
        if not chinese or not arabic:
            continue
        aliases = _latin_aliases(columns[2:6])
        if not aliases:
            fallback = _arabic_as_latin(arabic)
            aliases = (fallback,) if len(_normalize_latin(fallback)) >= 4 else ()
        entries.append(GlossaryEntry(chinese, arabic, aliases))
    return tuple(entries)


GLOSSARY = load_glossary()


def _build_latin_alias_index() -> tuple[
    dict[str, tuple[GlossaryEntry, ...]],
    dict[str, tuple[str, ...]],
]:
    by_alias: dict[str, list[GlossaryEntry]] = {}
    for entry in GLOSSARY:
        for alias in entry.latin_aliases:
            key = _normalize_latin(alias)
            if len(key) >= 3:
                by_alias.setdefault(key, []).append(entry)
    by_first: dict[str, list[str]] = {}
    for alias in by_alias:
        by_first.setdefault(alias[0], []).append(alias)
    return (
        {alias: tuple(entries) for alias, entries in by_alias.items()},
        {
            first: tuple(sorted(aliases, key=len, reverse=True))
            for first, aliases in by_first.items()
        },
    )


LATIN_ALIAS_ENTRIES, LATIN_ALIASES_BY_FIRST = _build_latin_alias_index()
ARABIC_SINGLE_TERMS = tuple(
    entry
    for entry in GLOSSARY
    if " " not in entry.uyghur_arabic and len(_normalize_arabic(entry.uyghur_arabic)) >= 5
)
ARABIC_SINGLE_NORMALIZED = {
    _normalize_arabic(entry.uyghur_arabic): entry for entry in ARABIC_SINGLE_TERMS
}
ARABIC_SINGLE_BY_LENGTH: dict[int, tuple[GlossaryEntry, ...]] = {}
for _entry in ARABIC_SINGLE_TERMS:
    _length = len(_normalize_arabic(_entry.uyghur_arabic))
    ARABIC_SINGLE_BY_LENGTH.setdefault(_length, tuple())
    ARABIC_SINGLE_BY_LENGTH[_length] += (_entry,)


def _term_pair(entry: GlossaryEntry) -> tuple[str, str]:
    return entry.uyghur_arabic, entry.chinese


def terminology_for_chinese_text(text: str, limit: int = 10) -> list[tuple[str, str]]:
    """Return glossary pairs whose standard Chinese term occurs in text."""
    found = [entry for entry in GLOSSARY if entry.chinese and entry.chinese in (text or "")]
    found.sort(key=lambda item: len(item.chinese), reverse=True)
    result: list[tuple[str, str]] = []
    for entry in found:
        pair = _term_pair(entry)
        if pair not in result:
            result.append(pair)
        if len(result) >= limit:
            break
    return result


def terminology_from_corrections(corrections: list[dict], limit: int = 10) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for item in corrections or ():
        standard = item.get("standard") if isinstance(item, dict) else None
        chinese = item.get("chinese") if isinstance(item, dict) else None
        if isinstance(standard, str) and isinstance(chinese, str) and standard.strip() and chinese.strip():
            pair = (standard.strip(), chinese.strip())
            if pair not in result:
                result.append(pair)
        if len(result) >= limit:
            break
    return result


def correct_arabic_text(text: str) -> dict:
    """Conservatively normalize typed Arabic Uyghur with the same glossary.

    Exact phrase matches are retained as standard spellings. Fuzzy replacement
    is limited to single agriculture terms with a >=0.94 score and a clear
    winner, which avoids rewriting ordinary words merely to force a match.
    """
    source = (text or "").strip()
    if not source or not GLOSSARY:
        return {
            "transcription_arabic": source,
            "corrections": [],
            "glossary_loaded": bool(GLOSSARY),
        }

    normalized_source = _normalize_arabic(source)
    corrected = source
    corrections: list[dict[str, str]] = []

    # Exact multi-word and single-word terms first, longest first.
    for entry in sorted(GLOSSARY, key=lambda item: len(item.uyghur_arabic), reverse=True):
        standard = entry.uyghur_arabic
        if not standard or _normalize_arabic(standard) not in normalized_source:
            continue
        pattern = re.compile(re.escape(standard), re.IGNORECASE)
        if pattern.search(corrected):
            corrected = pattern.sub(standard, corrected)
            pair = {"heard": standard, "standard": standard, "chinese": entry.chinese}
            if pair not in corrections:
                corrections.append(pair)

    # Fuzzy matching is intentionally restricted to standalone tokens.
    token_pattern = re.compile(r"[\u0600-\u06ff\u0750-\u077f]+")
    pieces: list[str] = []
    cursor = 0
    for match in token_pattern.finditer(corrected):
        pieces.append(corrected[cursor:match.start()])
        heard = match.group()
        heard_norm = _normalize_arabic(heard)
        if heard_norm in ARABIC_SINGLE_NORMALIZED:
            pieces.append(heard)
            cursor = match.end()
            continue
        ranked: list[tuple[float, GlossaryEntry]] = []
        candidates_for_length = (
            ARABIC_SINGLE_BY_LENGTH.get(len(heard_norm) - 1, ())
            + ARABIC_SINGLE_BY_LENGTH.get(len(heard_norm), ())
            + ARABIC_SINGLE_BY_LENGTH.get(len(heard_norm) + 1, ())
        )
        for entry in candidates_for_length:
            term_norm = _normalize_arabic(entry.uyghur_arabic)
            if abs(len(term_norm) - len(heard_norm)) > 1:
                continue
            score = difflib.SequenceMatcher(None, heard_norm, term_norm).ratio()
            if score >= 0.94:
                ranked.append((score, entry))
        ranked.sort(key=lambda item: item[0], reverse=True)
        if ranked and (len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= 0.06):
            entry = ranked[0][1]
            pieces.append(entry.uyghur_arabic)
            corrections.append({"heard": heard, "standard": entry.uyghur_arabic, "chinese": entry.chinese})
        else:
            pieces.append(heard)
        cursor = match.end()
    pieces.append(corrected[cursor:])
    return {
        "transcription_arabic": "".join(pieces),
        "corrections": corrections[:10],
        "glossary_loaded": bool(GLOSSARY),
    }


def correct_transcription(transcription_latin: str) -> dict:
    """Replace only high-confidence glossary matches in a continuous ASR string."""
    source = transcription_latin or ""
    compact = _normalize_latin(source)
    if not compact or not GLOSSARY:
        return {
            "transcription_latin": source,
            "transcription_arabic": "",
            "corrections": [],
            "glossary_loaded": bool(GLOSSARY),
        }

    # Exact matches are always safe unless the table maps that spelling to
    # multiple different Chinese terms. Fuzzy matching requires a very high
    # score and a clear winner to avoid changing ordinary speech by guesswork.
    matches: list[tuple[int, int, GlossaryEntry, str]] = []
    position = 0
    while position < len(compact):
        exact = []
        aliases = LATIN_ALIASES_BY_FIRST.get(compact[position], ())
        for alias in aliases:
            entries = LATIN_ALIAS_ENTRIES[alias]
            if compact.startswith(alias, position):
                unique = {(entry.chinese, entry.uyghur_arabic): entry for entry in entries}
                if len(unique) == 1:
                    exact.append((len(alias), next(iter(unique.values())), alias))
        if exact:
            length, entry, alias = max(exact, key=lambda item: item[0])
            matches.append((position, position + length, entry, alias))
            position += length
            continue

        candidates: dict[tuple[str, str], tuple[float, GlossaryEntry, str, int]] = {}
        # Limit fuzzy comparisons to glossary aliases with the same first
        # character.  At the >=0.92 threshold an initial-character mismatch
        # is not a safe agriculture-term correction, and this index makes the
        # common voice path tens of times cheaper than scanning every entry.
        for alias in aliases:
            entries = LATIN_ALIAS_ENTRIES[alias]
            if len(alias) < 5:
                continue
            for length in range(max(5, len(alias) - 1), min(len(compact) - position, len(alias) + 1) + 1):
                candidate = compact[position:position + length]
                score = difflib.SequenceMatcher(None, candidate, alias).ratio()
                if score < 0.92:
                    continue
                unique = {(entry.chinese, entry.uyghur_arabic): entry for entry in entries}
                if len(unique) != 1:
                    continue
                entry = next(iter(unique.values()))
                key = (entry.chinese, entry.uyghur_arabic)
                previous = candidates.get(key)
                if previous is None or score > previous[0]:
                    candidates[key] = (score, entry, alias, length)
        ranked = sorted(candidates.values(), key=lambda item: item[0], reverse=True)
        if ranked and (len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= 0.08):
            score, entry, alias, length = ranked[0]
            matches.append((position, position + length, entry, alias))
            position += length
        else:
            position += 1

    if not matches:
        from gheyret_uyghur_asr import latin_to_uyghur_arabic
        return {
            "transcription_latin": source,
            "transcription_arabic": latin_to_uyghur_arabic(source),
            "corrections": [],
            "glossary_loaded": bool(GLOSSARY),
        }

    # Map normalized compact offsets back to source character boundaries. The
    # ASR model emits Latin letters without spaces, but this also tolerates
    # spaces/diacritics in model variants.
    source_map: list[tuple[int, int]] = []
    for index, char in enumerate(source):
        normalized = _normalize_latin(char)
        source_map.extend((index, index + 1) for _ in normalized)

    from gheyret_uyghur_asr import latin_to_uyghur_arabic

    corrected_arabic_parts: list[str] = []
    corrections: list[dict[str, str]] = []
    source_cursor = 0
    compact_cursor = 0
    for start, end, entry, alias in matches:
        if start < compact_cursor:
            continue
        original_start = source_map[start][0]
        original_end = source_map[end - 1][1]
        prefix = latin_to_uyghur_arabic(source[source_cursor:original_start])
        if prefix and not prefix[-1].isspace():
            prefix += " "
        corrected_arabic_parts.append(prefix)
        corrected_arabic_parts.append(entry.uyghur_arabic + " ")
        heard = source[original_start:original_end]
        corrections.append({
            "heard": heard,
            "standard": entry.uyghur_arabic,
            "chinese": entry.chinese,
        })
        source_cursor = original_end
        compact_cursor = end
    corrected_arabic_parts.append(latin_to_uyghur_arabic(source[source_cursor:]))
    return {
        "transcription_latin": source,
        "transcription_arabic": "".join(corrected_arabic_parts).strip(),
        "corrections": corrections,
        "glossary_loaded": bool(GLOSSARY),
    }
