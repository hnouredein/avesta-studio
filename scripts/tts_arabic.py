"""
Arabic AI Voiceover Generator + Pronunciation Normalizer + Studio Mastering.

Uses Microsoft Edge Neural Arabic voices (edge-tts) with Arabic text normalization
so punctuation, numbers, percentages, and English terms are pronounced naturally,
then masters the audio via master_audio.py (-14 LUFS + Voice Preset).
"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

VOICE_MAP = {
    "salma": "ar-EG-SalmaNeural",
    "shakir": "ar-EG-ShakirNeural",
    "zariyah": "ar-SA-ZariyahNeural",
    "hamed": "ar-SA-HamedNeural",
}

# Strip emojis so TTS doesn't try to skip or read unicode symbols awkwardly
EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U00002600-\U000026FF\uFE0F\u200D]+",
    flags=re.UNICODE,
)

# Common Egyptian/Arabic pronunciation tweaks & diacritization for clean TTS delivery
PRONUNCIATION_REPLACEMENTS = [
    (r"%", " في المئة "),
    (r"\$", " دولار "),
    (r"ج\.م", " جنيه مصري "),
    (r"د\.إ", " درهم "),
    (r"ر\.س", " ريال "),
    (r"\bAI\b", "الذكاء الاصطناعي"),
    (r"\bChatGPT\b", "شات جي بي تي"),
    (r"\bTikTok\b", "تيك توك"),
    (r"\bReels\b", "ريلز"),
    (r"\bShorts\b", "شورتس"),
    (r"\bYouTube\b", "يوتيوب"),
    (r"\bInstagram\b", "إنستغرام"),
    (r"\bFacebook\b", "فيسبوك"),
]

# Diacritize common unvoweled Arabic/Egyptian words that TTS often guesses wrong
ARABIC_DIACRITICS_MAP = {
    "غناوي": "غَنَاوِي",
    "هلنا": "هَلْنَا",
    "مصر": "مِصْر",
    "المصرية": "المِصْرِيَّة",
    "الهوية": "الهَوِيَّة",
    "تراث": "تُرَاث",
    "التراث": "التُّرَاث",
    "شعر": "شِعْر",
    "الشعر": "الشِّعْر",
    "حكاية": "حِكَايَة",
    "قصة": "قِصَّة",
    "الفيديو": "الفِيديُو",
    "فيديو": "فِيديُو",
    "الجميل": "الجَمِيل",
    "النهاية": "النِّهَايَة",
    "نهاية": "نِهَايَة",
    "جديدة": "جَدِيدَة",
    "جديد": "جَدِيد",
    "أهلا": "أَهْلاً",
    "أهلاً": "أَهْلاً",
    "بكم": "بِكُمْ",
    "بيكم": "بِيكُمْ",
    "تابعونا": "تَابِعُونَا",
    "شوفوا": "شُوفُوا",
    "النهارده": "النَّهَارْدَه",
    "النهاردة": "النَّهَارْدَه",
    "علشان": "عَلَشَان",
    "عشان": "عَشَان",
}


def normalize_arabic_for_tts(raw_text: str) -> str:
    """Clean and normalize Arabic text for natural AI speech pronunciation."""
    text = EMOJI_RE.sub(" ", raw_text or "")
    for pattern, repl in PRONUNCIATION_REPLACEMENTS:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    # Apply word-level diacritics only when the word doesn't already have harakat
    tokens = text.split()
    fixed_tokens = []
    for tok in tokens:
        stripped = tok.strip("،,.!؟?\"'()")
        if stripped in ARABIC_DIACRITICS_MAP:
            fixed_tokens.append(tok.replace(stripped, ARABIC_DIACRITICS_MAP[stripped], 1))
        else:
            fixed_tokens.append(tok)
    text = " ".join(fixed_tokens)
    # Normalize punctuation so Edge-TTS inserts natural breathing pauses
    text = text.replace("...", "، ").replace("…", "، ")
    text = re.sub(r"\s*([،,.!؟?])\s*", r"\1 ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def synthesize_edge_tts(text: str, voice_id: str, rate: str, out_mp3: str) -> list[dict]:
    import edge_tts

    last_err = None
    for attempt in range(2):
        try:
            communicate = edge_tts.Communicate(text, voice_id, rate=rate, boundary="WordBoundary")
            words: list[dict] = []
            audio_bytes = 0
            with open(out_mp3, "wb") as audio_file:
                async for chunk in communicate.stream():
                    ctype = chunk.get("type")
                    if ctype == "audio":
                        data = chunk["data"]
                        audio_file.write(data)
                        audio_bytes += len(data)
                    elif ctype == "WordBoundary":
                        offset_s = round(chunk.get("offset", 0) / 10_000_000.0, 3)
                        dur_s = round(chunk.get("duration", 2000000) / 10_000_000.0, 3)
                        word_txt = (chunk.get("text") or "").strip()
                        if word_txt:
                            words.append({
                                "word": word_txt,
                                "start": offset_s,
                                "end": round(offset_s + max(0.12, dur_s), 3),
                            })
            if audio_bytes > 0:
                return words
            raise RuntimeError("لم يصل صوت من الخدمة — تأكد من النص والإنترنت.")
        except Exception as exc:
            last_err = exc
            if attempt == 0:
                await asyncio.sleep(0.8)
    raise last_err  # type: ignore[misc]


def enhance_with_pedalboard(wav_path: str, preset: str) -> bool:
    """Apply Spotify Pedalboard studio warmth, de-harshing, and gentle limiting to TTS audio."""
    if preset == "raw":
        return False
    try:
        from pedalboard import (
            HighpassFilter,
            HighShelfFilter,
            Limiter,
            LowpassFilter,
            LowShelfFilter,
            Pedalboard,
            Reverb,
        )
        from pedalboard.io import AudioFile
    except ImportError:
        return False

    effects = [
        HighpassFilter(cutoff_frequency_hz=75),
        LowShelfFilter(cutoff_frequency_hz=175, gain_db=2.4 if preset == "podcast" else 1.6),
        HighShelfFilter(cutoff_frequency_hz=7500, gain_db=-2.2),
        LowpassFilter(cutoff_frequency_hz=13500),
    ]
    if preset == "heritage_reverb":
        effects.append(Reverb(room_size=0.18, damping=0.65, wet_level=0.08, dry_level=0.92))
    effects.append(Limiter(threshold_db=-1.5, release_ms=80.0))

    board = Pedalboard(effects)
    with AudioFile(wav_path) as f:
        audio = f.read(f.frames)
        sr = f.samplerate
    processed = board(audio, sr)
    with AudioFile(wav_path, "w", sr, processed.shape[0]) as f:
        f.write(processed)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate mastered Arabic AI voiceover.")
    parser.add_argument("--text", required=True, help="Arabic/English script text")
    parser.add_argument("--out", required=True, help="Output mastered WAV path")
    parser.add_argument("--words-out", default="", help="Optional JSON path for word timestamps")
    parser.add_argument("--voice", default="salma", help="Voice key or full edge-tts voice ID")
    parser.add_argument("--rate", default="+0%", help="Speech rate e.g. +0%, +10%, -10%")
    parser.add_argument("--preset", default="studio", help="master_audio.py preset")
    args = parser.parse_args()

    clean_text = normalize_arabic_for_tts(args.text)
    if not clean_text:
        print("ERROR: النص فارغ بعد التنظيف.", file=sys.stderr)
        sys.exit(1)

    voice_id = VOICE_MAP.get(args.voice.lower(), args.voice)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    raw_mp3 = args.out + ".raw.mp3"

    try:
        words = asyncio.run(synthesize_edge_tts(clean_text, voice_id, args.rate, raw_mp3))
    except Exception as exc:
        print(f"تعذّر توليد الصوت من الخدمة (تأكد من الإنترنت أو جرّب نصاً أوضح): {exc}", file=sys.stderr)
        sys.exit(1)

    # Convert cleanly to 48kHz stereo WAV, then polish with Spotify Pedalboard
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-i", raw_mp3,
        "-vn",
        "-ar", "48000",
        "-ac", "2",
        args.out,
    ]
    res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        print(res.stderr, file=sys.stderr)
        sys.exit(res.returncode)

    enhanced = enhance_with_pedalboard(args.out, args.preset)
    print(f"Pedalboard enhanced: {enhanced}", flush=True)

    if os.path.exists(raw_mp3):
        os.remove(raw_mp3)

    if args.words_out and words:
        with open(args.words_out, "w", encoding="utf-8") as wf:
            json.dump(words, wf, ensure_ascii=False, indent=2)

    print(f"TTS_OK:{args.out} ({len(words)} words)", flush=True)


if __name__ == "__main__":
    main()
