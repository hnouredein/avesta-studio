"""
Post-process word-level transcripts (from HyperFrames / Whisper JSON) for Arabic Reels:
  1. Applies custom glossary corrections defined in brand.md (e.g. "أنتي جرافيتي" -> "Antigravity").
  2. Detects silences longer than --min-silence (default 0.4s) and proposes cuts with --pad (default 0.1s).
  3. Groups words into mobile-friendly 3-4 word caption chunks.
  4. Wraps mixed English/Latin tokens with Unicode First Strong Isolate (U+2068..U+2069)
     so English words never jump out of order inside RTL Arabic captions.

Usage:
  python scripts/clean_transcript.py transcript.json --brand brand.md --out cleaned_captions.json
"""

import argparse
import json
import os
import re
import sys
from typing import Any


LATIN_TOKEN_RE = re.compile(r"([A-Za-z0-9][A-Za-z0-9@#._+\-/]*[A-Za-z0-9]|[A-Za-z0-9]+)")
FILLER_WORDS = {"امم", "اممم", "آآ", "يعني يعني", "اه", "أه", "umm", "uh", "uhh", "erm"}


def load_glossary_from_brand(brand_path: str) -> dict[str, str]:
    """Parse 'wrong -> right' lines inside the Glossary section of brand.md."""
    glossary: dict[str, str] = {}
    if not brand_path or not os.path.exists(brand_path):
        return glossary
    with open(brand_path, "r", encoding="utf-8-sig") as f:
        text = f.read()
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            in_section = ("glossary" in stripped.lower()) or ("قاموس" in stripped)
            continue
        if in_section and "->" in stripped:
            cleaned = stripped.lstrip("-*• ").strip()
            parts = cleaned.split("->", 1)
            if len(parts) == 2:
                src = parts[0].strip().strip("`\"'")
                dst = parts[1].strip().strip("`\"'")
                if src and dst:
                    glossary[src] = dst
    return glossary


def isolate_latin_for_rtl(text: str) -> str:
    """Wrap English words/numbers in Unicode LRI..PDI so RTL rendering stays exact."""
    # U+2066 LEFT-TO-RIGHT ISOLATE, U+2069 POP DIRECTIONAL ISOLATE
    return LATIN_TOKEN_RE.sub(lambda m: f"\u2066{m.group(0)}\u2069", text)


def extract_words(data: Any) -> list[dict[str, Any]]:
    """Support common Whisper / HyperFrames JSON transcript formats."""
    words: list[dict[str, Any]] = []
    if isinstance(data, dict):
        if "words" in data and isinstance(data["words"], list):
            raw_words = data["words"]
        elif "segments" in data and isinstance(data["segments"], list):
            raw_words = []
            for seg in data["segments"]:
                if isinstance(seg, dict) and "words" in seg:
                    raw_words.extend(seg["words"])
                elif isinstance(seg, dict) and "text" in seg:
                    raw_words.append(seg)
        else:
            raw_words = []
    elif isinstance(data, list):
        raw_words = data
    else:
        raw_words = []

    for item in raw_words:
        if not isinstance(item, dict):
            continue
        txt = (item.get("word") or item.get("text") or "").strip()
        if not txt:
            continue
        start = float(item.get("start", item.get("startTime", 0.0)))
        end = float(item.get("end", item.get("endTime", start + 0.2)))
        words.append({"word": txt, "start": round(start, 3), "end": round(end, 3)})
    return words


def apply_glossary(words: list[dict[str, Any]], glossary: dict[str, str]) -> list[dict[str, Any]]:
    if not glossary or not words:
        return words
    # 1. Handle multi-word phrases first (e.g. "أنتي جرافيتي" -> "Antigravity")
    multi = [(k.split(), v) for k, v in glossary.items() if " " in k]
    multi.sort(key=lambda item: len(item[0]), reverse=True)
    merged: list[dict[str, Any]] = []
    i = 0
    while i < len(words):
        matched = False
        for parts, replacement in multi:
            n = len(parts)
            if i + n <= len(words):
                window = [words[i + j]["word"].strip(".,،!?؟") for j in range(n)]
                if window == parts:
                    merged.append({
                        "word": replacement,
                        "start": words[i]["start"],
                        "end": words[i + n - 1]["end"],
                    })
                    i += n
                    matched = True
                    break
        if not matched:
            merged.append(words[i].copy())
            i += 1
    # 2. Handle single-word replacements
    single = {k: v for k, v in glossary.items() if " " not in k}
    for w in merged:
        token = w["word"]
        for wrong, right in single.items():
            if wrong in token:
                token = token.replace(wrong, right)
        w["word"] = token
    return merged


def detect_cuts(words: list[dict[str, Any]], min_silence: float, pad: float) -> list[dict[str, Any]]:
    cuts: list[dict[str, Any]] = []
    for i in range(len(words) - 1):
        gap = words[i + 1]["start"] - words[i]["end"]
        if gap >= min_silence:
            cut_start = round(words[i]["end"] + pad, 3)
            cut_end = round(words[i + 1]["start"] - pad, 3)
            if cut_end > cut_start + 0.05:
                cuts.append({
                    "type": "silence",
                    "start": cut_start,
                    "end": cut_end,
                    "duration": round(cut_end - cut_start, 3),
                    "reason": f"Silence {gap:.2f}s (padded {pad}s)",
                })
    for i, w in enumerate(words):
        norm = re.sub(r"[^\w\u0600-\u06FF]", "", w["word"].lower())
        if norm in FILLER_WORDS:
            cuts.append({
                "type": "filler",
                "start": max(0.0, round(w["start"] - pad, 3)),
                "end": round(w["end"] + pad, 3),
                "word": w["word"],
                "reason": "Filler word",
            })
        elif i > 0 and norm and norm == re.sub(r"[^\w\u0600-\u06FF]", "", words[i - 1]["word"].lower()):
            cuts.append({
                "type": "repeat",
                "start": w["start"],
                "end": w["end"],
                "word": w["word"],
                "reason": "Repeated word",
            })
    return cuts


MERGE_ORPHAN_LAST = False  # set per run (settings mergeOrphanCaption): fold a lone final word into the previous caption


def build_chunks(words: list[dict[str, Any]], max_words: int = 4, max_gap: float = 0.5) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    buf: list[dict[str, Any]] = []

    def flush() -> None:
        if not buf:
            return
        raw_text = " ".join(x["word"] for x in buf)
        chunks.append({
            "start": buf[0]["start"],
            "end": buf[-1]["end"],
            "text": raw_text,
            "rtl_text": isolate_latin_for_rtl(raw_text),
            "words": buf.copy(),
        })
        buf.clear()

    for w in words:
        if buf and (len(buf) >= max_words or (w["start"] - buf[-1]["end"]) > max_gap):
            flush()
        buf.append(w)
        if w["word"].endswith((".", "!", "?", "؟", "،", ",")):
            flush()
    flush()
    if MERGE_ORPHAN_LAST and len(chunks) >= 2 and len(chunks[-1]["words"]) == 1:
        last = chunks.pop()
        prev = chunks[-1]
        if last["start"] - prev["end"] <= max_gap and not prev["words"][-1]["word"].endswith((".", "!", "?", "؟", "،", ",")):
            prev["words"] = prev["words"] + last["words"]
            prev["end"] = last["end"]
            prev["text"] = " ".join(x["word"] for x in prev["words"])
            prev["rtl_text"] = isolate_latin_for_rtl(prev["text"])
        else:
            chunks.append(last)
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean Arabic/mixed transcripts for HyperFrames Reels.")
    parser.add_argument("input", help="Input transcript JSON file")
    parser.add_argument("--brand", default="brand.md", help="Path to brand.md with optional glossary")
    parser.add_argument("--out", required=True, help="Output JSON file with chunks and proposed cuts")
    parser.add_argument("--max-words", type=int, default=4, help="Max words per caption chunk (default: 4)")
    parser.add_argument("--min-silence", type=float, default=0.4, help="Silence threshold in seconds (default: 0.4)")
    parser.add_argument("--pad", type=float, default=0.1, help="Safety padding around cuts in seconds (default: 0.1)")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    glossary = load_glossary_from_brand(args.brand)
    words = apply_glossary(extract_words(data), glossary)
    cuts = detect_cuts(words, args.min_silence, args.pad)
    chunks = build_chunks(words, max_words=args.max_words)

    result = {
        "glossary_applied": len(glossary),
        "total_words": len(words),
        "proposed_cuts": cuts,
        "caption_chunks": chunks,
        "full_text": " ".join(w["word"] for w in words),
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Processed {len(words)} words -> {len(chunks)} caption chunks, {len(cuts)} proposed cuts.")
    print(f"Saved to: {args.out}")


if __name__ == "__main__":
    main()
