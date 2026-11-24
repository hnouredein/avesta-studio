"""
Avesta AI Video Studio — 100% Free Autonomous 1-Click Local Video Editing Engine.

Modes:
  --mode full      : Full 6-stage pipeline (Audio Mastering -> Color Grading -> Whisper
                     Transcription -> Smart Silence Cuts + Glossary -> HyperFrames Render
                     + Cover Thumbnail -> Auto-Ducking Music/SFX Mix + post.txt)
  --mode rerender  : Fast re-render after editing captions/hook/CTA/music in the UI
                     (skips Stages 1-4, runs Stage 5 + Stage 6 only)
  --mode prep      : Stages 1-2 only (Audio Mastering + Color Grading)

Emits structured progress lines (`@STAGE <n>/6 <pct> <label>`) for the Studio UI.
"""

import argparse
import array
import glob
import hashlib
import json
import time
import math
import os
import re
import shutil
import subprocess
import sys
from typing import Any

import urllib.parse
import urllib.request

# Allow UTF-8 stdout on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
HF_CLI = os.path.join(ROOT_DIR, ".agents", "skills", "hyperframes", "scripts", "plugin-cli.mjs")


def resolve_hf_cmd() -> list[str]:
    """Use locally cached hyperframes CLI binary directly (~0.8s startup vs ~17s npx lookup)."""
    candidates: list[tuple[tuple[int, ...], str]] = []
    search_roots = []
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        search_roots.append(os.path.join(local_app, "npm-cache", "_npx"))
    home_dir = os.path.expanduser("~")
    if home_dir:
        search_roots.append(os.path.join(home_dir, ".npm", "_npx"))

    for base in search_roots:
        if not os.path.isdir(base):
            continue
        for pkg_json in glob.glob(os.path.join(base, "*", "node_modules", "hyperframes", "package.json")):
            try:
                with open(pkg_json, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                ver_str = str(meta.get("version") or "0.0.0").split("-")[0]
                ver_tuple = tuple(int(p) for p in ver_str.split(".")[:3])
                if ver_tuple < (0, 9, 68):
                    continue
                bin_field = meta.get("bin")
                bin_rel = bin_field.get("hyperframes") if isinstance(bin_field, dict) else bin_field
                if not bin_rel:
                    continue
                bin_abs = os.path.normpath(os.path.join(os.path.dirname(pkg_json), bin_rel))
                if os.path.exists(bin_abs):
                    candidates.append((ver_tuple, bin_abs))
            except Exception:
                continue

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return ["node", candidates[0][1]]
    return ["node", HF_CLI]


def optimal_render_workers() -> int:
    """Pick empirically optimal worker count (leaves 1 core free for GPU encoder & OS)."""
    cores = os.cpu_count() or 2
    if cores >= 6:
        return 4
    if cores >= 4:
        return 3
    if cores >= 2:
        return 2
    return 1


def compute_audio_master_sig(settings: dict[str, Any]) -> str:
    payload = {
        "voicePreset": str(settings.get("voicePreset", "studio") or "studio"),
        "denoise": str(settings.get("denoise", "light") or "light"),
        "lufs": round(float(settings.get("lufs", -14) or -14), 2),
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]

sys.path.insert(0, SCRIPTS_DIR)
import build_hyperframes  # noqa: E402
import clean_transcript  # noqa: E402
import smart_crop  # noqa: E402


def emit_stage(step: int, total: int, pct: int, message: str) -> None:
    print(f"@STAGE {step}/{total} {pct} {message}", flush=True)


def run_cmd(cmd: list[str], cwd: str | None = None, capture: bool = False) -> subprocess.CompletedProcess:
    if capture:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out_lines = []
    assert proc.stdout is not None
    for line in proc.stdout:
        stripped = line.rstrip()
        if stripped:
            print(stripped, flush=True)
            out_lines.append(stripped)
    code = proc.wait()
    return subprocess.CompletedProcess(cmd, code, "\n".join(out_lines), "")


def probe_media(path: str) -> dict[str, Any]:
    res = run_cmd(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration:stream=codec_type,width,height",
            "-of", "json",
            path,
        ],
        capture=True,
    )
    if res.returncode != 0:
        return {"duration": 5.0, "has_audio": False, "width": 1080, "height": 1920}
    data = json.loads(res.stdout)
    streams = data.get("streams", [])
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    vstream = next((s for s in streams if s.get("codec_type") == "video"), {})
    dur = float(data.get("format", {}).get("duration", 5.0))
    return {
        "duration": dur,
        "has_audio": has_audio,
        "width": vstream.get("width", 1080),
        "height": vstream.get("height", 1920),
    }


def ensure_audio_stream(input_mp4: str, output_mp4: str) -> bool:
    """If input video has no audio track, attach silent stereo 48kHz AAC so pipeline never breaks."""
    info = probe_media(input_mp4)
    if info["has_audio"]:
        return True
    print("ℹ️ الفيديو بدون صوت — جاري إضافة مسار صوت صامت للتوافق مع المونتاج...", flush=True)
    res = run_cmd(
        [
            "ffmpeg", "-y",
            "-i", input_mp4,
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-c:v", "copy", "-c:a", "aac", "-shortest",
            output_mp4,
        ],
        capture=True,
    )
    if res.returncode != 0:
        raise RuntimeError(f"Failed adding silent audio track: {res.stderr}")
    return False


def detect_silences_ffmpeg(video_path: str, min_silence: float) -> list[tuple[float, float]]:
    """Detect silent ranges [(start, end), ...] via FFmpeg silencedetect."""
    res = run_cmd(
        [
            "ffmpeg", "-i", video_path,
            "-af", f"silencedetect=noise=-32dB:d={min_silence:.2f}",
            "-f", "null", "-",
        ],
        capture=True,
    )
    log = (res.stdout or "") + "\n" + (res.stderr or "")
    silences: list[tuple[float, float]] = []
    cur_start: float | None = None
    for line in log.splitlines():
        m_start = re.search(r"silence_start:\s*([0-9.]+)", line)
        if m_start:
            cur_start = float(m_start.group(1))
        m_end = re.search(r"silence_end:\s*([0-9.]+)", line)
        if m_end and cur_start is not None:
            silences.append((cur_start, float(m_end.group(1))))
            cur_start = None
    return silences


def compute_keep_segments(
    duration: float,
    silences: list[tuple[float, float]],
    pad: float,
) -> list[tuple[float, float]]:
    """Invert silence ranges into kept speech segments with safety padding."""
    if not silences or duration <= 1.0:
        return [(0.0, duration)]

    cuts: list[tuple[float, float]] = []
    for s_start, s_end in silences:
        c_start = max(0.0, s_start + pad)
        c_end = min(duration, s_end - pad)
        if c_end - c_start >= 0.15:
            cuts.append((c_start, c_end))

    if not cuts:
        return [(0.0, duration)]

    keeps: list[tuple[float, float]] = []
    cursor = 0.0
    for c_start, c_end in cuts:
        if c_start > cursor + 0.05:
            keeps.append((round(cursor, 3), round(c_start, 3)))
        cursor = max(cursor, c_end)
    if duration > cursor + 0.05:
        keeps.append((round(cursor, 3), round(duration, 3)))

    kept_total = sum(e - s for s, e in keeps)
    # Never cut if almost the whole video would vanish or < 0.35s saved
    if kept_total < max(1.0, duration * 0.25) or (duration - kept_total) < 0.35:
        return [(0.0, duration)]
    return keeps


def cut_video_by_segments(
    src_mp4: str,
    dst_mp4: str,
    keeps: list[tuple[float, float]],
    orig_dur: float,
) -> None:
    if len(keeps) == 1 and keeps[0][0] <= 0.05 and keeps[0][1] >= orig_dur - 0.12:
        shutil.copy2(src_mp4, dst_mp4)
        return

    filters = []
    concat_in = []
    for i, (s, e) in enumerate(keeps):
        filters.append(f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{i}]")
        filters.append(f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{i}]")
        concat_in.append(f"[v{i}][a{i}]")
    filters.append(f"{''.join(concat_in)}concat=n={len(keeps)}:v=1:a=1[vout][aout]")

    cmd = [
        "ffmpeg", "-y",
        "-i", src_mp4,
        "-filter_complex", ";".join(filters),
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "superfast", "-crf", "16", "-g", "30", "-keyint_min", "30", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        dst_mp4,
    ]
    res = run_cmd(cmd, capture=True)
    if res.returncode != 0:
        print(f"⚠️ تعذّر قصّ السكوت، سيتم الإبقاء على الفيديو كاملاً: {res.stderr[:300]}", flush=True)
        shutil.copy2(src_mp4, dst_mp4)


def remap_time(t: float, keeps: list[tuple[float, float]]) -> float:
    """Map an original timestamp onto the new cut timeline."""
    acc = 0.0
    for s, e in keeps:
        if t < s:
            return round(acc, 3)
        if s <= t <= e:
            return round(acc + (t - s), 3)
        acc += (e - s)
    return round(acc, 3)


def trim_input_video(
    src_mp4: str,
    dst_mp4: str,
    trim_start: float,
    trim_end: float,
    cut_segments: list[dict[str, Any]] | None = None,
) -> str:
    """Trim start/end timestamps AND physically remove any middle cut_segments cleanly via FFmpeg."""
    dur = probe_media(src_mp4).get("duration", 0.0)
    if dur <= 0.5:
        return src_mp4

    t0 = max(0.0, min(dur - 0.5, float(trim_start or 0.0)))
    raw_te = float(trim_end or 0.0)
    t1 = min(dur, raw_te) if raw_te > t0 + 0.4 else dur

    # Normalize & merge middle segments to remove
    cuts: list[tuple[float, float]] = []
    for seg in (cut_segments or []):
        if not isinstance(seg, dict):
            continue
        cs = max(t0, min(t1, float(seg.get("start") or 0.0)))
        ce = max(t0, min(t1, float(seg.get("end") or 0.0)))
        if ce > cs + 0.15:
            cuts.append((cs, ce))
    cuts.sort()

    merged_cuts: list[tuple[float, float]] = []
    for cs, ce in cuts:
        if merged_cuts and cs <= merged_cuts[-1][1] + 0.05:
            merged_cuts[-1] = (merged_cuts[-1][0], max(merged_cuts[-1][1], ce))
        else:
            merged_cuts.append((cs, ce))

    keeps: list[tuple[float, float]] = []
    cursor = t0
    for cs, ce in merged_cuts:
        if cs > cursor + 0.1:
            keeps.append((round(cursor, 3), round(cs, 3)))
        cursor = max(cursor, ce)
    if t1 > cursor + 0.1:
        keeps.append((round(cursor, 3), round(t1, 3)))

    if not keeps:
        return src_mp4
    if len(keeps) == 1 and keeps[0][0] <= 0.05 and keeps[0][1] >= dur - 0.12:
        return src_mp4

    print(f"✂️ قصّ الأجزاء المحددة من الفيديو: الإبقاء على {len(keeps)} مقطع/مقاطع.", flush=True)
    cut_video_by_segments(src_mp4, dst_mp4, keeps, dur)
    if os.path.exists(dst_mp4):
        return dst_mp4
    return src_mp4


def find_best_teaser_start(video_path: str, duration: float, teaser_dur: float) -> float:
    """Scan mono 8kHz PCM energy per 0.5s bin to pick the loudest/most engaging 3s teaser slice."""
    fallback = round(max(0.0, min(max(0.0, duration - teaser_dur), duration * 0.35)), 2)
    if duration <= teaser_dur + 1.0:
        return 0.0
    try:
        proc = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", video_path, "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
            capture_output=True,
            timeout=30,
        )
        raw = proc.stdout or b""
        if len(raw) < 16000:
            return fallback
        samples = array.array("h")
        samples.frombytes(raw[: len(raw) - (len(raw) % 2)])
        bin_size = 4000  # 0.5s at 8kHz
        bins: list[float] = []
        for i in range(0, len(samples), bin_size):
            chunk = samples[i : i + bin_size]
            if len(chunk) < bin_size // 2:
                break
            rms = math.sqrt(sum(s * s for s in chunk) / len(chunk))
            bins.append(rms)

        win = max(1, int(round(teaser_dur / 0.5)))
        start_bin = min(len(bins) - win, max(1, int(round(min(3.0, duration * 0.2) / 0.5))))
        end_bin = max(start_bin + 1, len(bins) - win + 1)
        if end_bin <= start_bin:
            return fallback

        best_idx = start_bin
        best_score = -1.0
        for idx in range(start_bin, end_bin):
            score = sum(bins[idx : idx + win]) / win
            if score > best_score:
                best_score = score
                best_idx = idx
        return round(min(max(0.0, duration - teaser_dur), best_idx * 0.5), 2)
    except Exception:
        return fallback


def prepend_teaser_hook(body_mp4: str, out_mp4: str, teaser_start: float, teaser_dur: float) -> bool:
    """Slice a viral teaser segment and prepend it smoothly before the main video."""
    ts = max(0.0, float(teaser_start))
    te = ts + max(1.5, float(teaser_dur))
    filter_complex = (
        f"[0:v]trim=start={ts:.3f}:end={te:.3f},setpts=PTS-STARTPTS[tv];"
        f"[0:a]atrim=start={ts:.3f}:end={te:.3f},asetpts=PTS-STARTPTS[ta];"
        f"[0:v]setpts=PTS-STARTPTS[bv];"
        f"[0:a]asetpts=PTS-STARTPTS[ba];"
        f"[tv][ta][bv][ba]concat=n=2:v=1:a=1[vout][aout]"
    )
    res = run_cmd(
        [
            "ffmpeg", "-y",
            "-i", body_mp4,
            "-filter_complex", filter_complex,
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "superfast", "-crf", "16", "-g", "30", "-keyint_min", "30", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart",
            out_mp4,
        ],
        capture=True,
    )
    if res.returncode != 0 or not os.path.exists(out_mp4):
        print(f"⚠️ تعذّر تركيب هوك الـ 3 ثواني: {res.stderr[:240]}", flush=True)
        return False
    return True


def apply_delogo_masks(src_mp4: str, dst_mp4: str, overlays: list[dict[str, Any]]) -> str:
    """Apply FFmpeg delogo filters for user-drawn watermark removal boxes."""
    masks = [o for o in (overlays or []) if isinstance(o, dict) and o.get("mode") == "delogo"]
    if not masks:
        return src_mp4

    info = probe_media(src_mp4)
    vid_w = max(64, int(info.get("width", 1080) or 1080))
    vid_h = max(64, int(info.get("height", 1920) or 1920))
    filters: list[str] = []
    for o in masks:
        x = max(2, min(vid_w - 14, int(round(vid_w * float(o.get("x", 5)) / 100.0))))
        y = max(2, min(vid_h - 14, int(round(vid_h * float(o.get("y", 5)) / 100.0))))
        w = max(8, min(vid_w - 2 - x, int(round(vid_w * float(o.get("w", 20)) / 100.0))))
        h = max(8, min(vid_h - 2 - y, int(round(vid_h * float(o.get("h", 8)) / 100.0))))
        st = max(0.0, float(o.get("start") or 0.0))
        en = max(0.0, float(o.get("end") or 0.0))
        enable = f":enable='between(t,{st:.3f},{en:.3f})'" if en > st else ""
        filters.append(f"delogo=x={x}:y={y}:w={w}:h={h}{enable}")

    res = run_cmd(
        [
            "ffmpeg", "-y",
            "-i", src_mp4,
            "-vf", ",".join(filters),
            "-c:v", "libx264", "-preset", "superfast", "-crf", "16", "-g", "30", "-keyint_min", "30", "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
            dst_mp4,
        ],
        capture=True,
    )
    if res.returncode != 0 or not os.path.exists(dst_mp4):
        print(f"⚠️ تعذّر تطبيق مسح اللوجو delogo: {res.stderr[:240]}", flush=True)
        return src_mp4
    return dst_mp4


def transcribe_with_hyperframes(video_path: str, work_dir: str, model: str, lang: str) -> list[dict[str, Any]]:
    """Run local Whisper via HyperFrames CLI (NDJSON) and return normalized [{word, start, end}]."""
    cmd = [
        *resolve_hf_cmd(),
        "transcribe",
        "--engine", "whisper",
        "--model", model,
        "--language", lang,
        "--json",
        "--no-runtime-install",
        "--timeout", "600000",
        video_path,
    ]
    print(f"🗣️ تشغيل Whisper محلياً (model={model}, lang={lang})...", flush=True)
    res = run_cmd(cmd, cwd=work_dir, capture=True)
    for _attempt in (2, 3):
        if res.returncode == 0:
            break
        print(f"⚠️ Whisper فشل (rc={res.returncode}) stderr_tail={res.stderr[-600:]!r} stdout_tail={(res.stdout or '')[-600:]!r} — إعادة المحاولة {_attempt}/3", flush=True)
        time.sleep(4)
        res = run_cmd(cmd, cwd=work_dir, capture=True)
    if res.returncode != 0:
        print(f"⚠️ تعذّر التفريغ الصوتي التلقائي (سيستمر المونتاج بدون ترجمة تلقائية): {res.stderr[-260:]}", flush=True)
        return []

    raw_out = (res.stdout or "").strip()
    stream_words: list[dict[str, Any]] = []
    transcript_file: str | None = None

    for line in raw_out.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("type") == "words" and isinstance(obj.get("words"), list):
            stream_words.extend(obj["words"])
        if obj.get("transcriptPath"):
            transcript_file = obj["transcriptPath"]

    parsed_payload: Any = stream_words
    if transcript_file and os.path.exists(transcript_file):
        try:
            with open(transcript_file, "r", encoding="utf-8-sig") as f:
                parsed_payload = json.load(f)
        except Exception:
            parsed_payload = stream_words

    raw_path = os.path.join(work_dir, "raw_transcript.json")
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(parsed_payload, f, ensure_ascii=False, indent=2)

    return clean_transcript.extract_words(parsed_payload)


def _gtx_once(text: str, sl: str, tl: str) -> str:
    q = urllib.parse.quote(text)
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={sl}&tl={tl}&dt=t&q={q}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return "".join(part[0] for part in (data[0] or []) if part and part[0]).strip()


def _alt_translate(text: str, sl: str, tl: str) -> str:
    """Second endpoint (Google dict-chrome-ex client)."""
    q = urllib.parse.quote(text)
    url = f"https://clients5.google.com/translate_a/t?client=dict-chrome-ex&sl={sl}&tl={tl}&q={q}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data and isinstance(data[0], list):
        data = [d[0] if isinstance(d, list) else d for d in data]
    return "".join(str(x) for x in data).strip()


def _mymemory_translate(text: str, sl: str, tl: str) -> str:
    q = urllib.parse.quote(text[:480])
    url = f"https://api.mymemory.translated.net/get?q={q}&langpair={sl}|{tl}"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return (data.get("responseData") or {}).get("translatedText", "").strip()


def _gtx_translate(text: str, sl: str, tl: str) -> str:
    """Translate with retries (3 x backoff) over three endpoints. Raises only if all fail."""
    last: Exception | None = None
    for attempt in range(3):
        for fn in (_gtx_once, _alt_translate, _mymemory_translate):
            try:
                out = fn(text, sl, tl)
                if out:
                    return out
            except Exception as e:  # noqa: BLE001
                last = e
                print(f"   (translate {fn.__name__} attempt {attempt + 1} failed: {type(e).__name__} {e})", flush=True)
        time.sleep(1.5 * (attempt + 1))
    raise last or RuntimeError("translate failed")


ENGLISH_FIXES: dict[str, str] = {}  # per-run English replacements (settings_json: englishFixes), applied after translation


def populate_bilingual_captions(captions: list[dict[str, Any]], src_lang: str = "ar") -> None:
    """Translate captions to English (or Arabic if source is English) for bilingual subtitles."""
    if not captions:
        return
    sl = "en" if str(src_lang).lower().startswith("en") else "ar"
    tl = "ar" if sl == "en" else "en"
    missing = [ch for ch in captions if (ch.get("text") or "").strip() and not (ch.get("en_text") or "").strip()]
    if not missing:
        return

    # Batch translate chunks in groups of 12 to minimize HTTP calls
    for start_i in range(0, len(missing), 12):
        batch = missing[start_i : start_i + 12]
        sep = "\n@@\n"
        joined = sep.join((c.get("text") or "").strip() for c in batch)
        translated_parts: list[str] | None = None
        try:
            res = _gtx_translate(joined, sl, tl)
            parts = [p.strip() for p in re.split(r"\n*\s*@@\s*\n*", res)]
            if len(parts) == len(batch):
                translated_parts = parts
        except Exception:
            translated_parts = None

        for idx_b, ch in enumerate(batch):
            orig = (ch.get("text") or "").strip()
            if translated_parts is not None:
                tr = translated_parts[idx_b]
            else:
                try:
                    tr = _gtx_translate(orig, sl, tl)
                except Exception:
                    tr = ""
            if sl == "en":
                # Keep Arabic on top, English underneath
                ch["en_text"] = orig
                if tr:
                    ch["text"] = tr
            else:
                for _a, _b in ENGLISH_FIXES.items():
                    tr = tr.replace(_a, _b)
                ch["en_text"] = tr
            if not (ch.get("en_text") or "").strip() and sl != "en":
                print("   (no English translation for caption: " + orig[:30] + ")", flush=True)


def load_combined_glossary(brand: dict[str, Any]) -> dict[str, str]:
    glossary = clean_transcript.load_glossary_from_brand(os.path.join(ROOT_DIR, "brand.md"))
    for item in brand.get("glossary", []):
        w = (item.get("wrong") or "").strip()
        r = (item.get("right") or "").strip()
        if w and r:
            glossary[w] = r
    return glossary


def is_generic_video_name(raw_name: str) -> bool:
    """Return True if a title/filename is meaningless (IDs, SnapTik, VID_..., download, etc.)."""
    s = (raw_name or "").strip()
    if not s or len(s) < 3:
        return True
    low = s.lower()
    if low in ("فيديو جديد", "فيديو من رابط...", "فيديو من رابط", "video", "output", "input", "clip", "reel", "short"):
        return True
    if re.match(
        r"^(\d{2}-|video[-_ ]?|new-video|my-video|url-video|youtube-video|tiktok-video|facebook-video|instagram-video|"
        r"vid[-_]|img[-_]|pxl[-_]|dji[-_]|screen|whatsapp|download|snaptik|ssstik|saveinsta|savett|tikmate|fbdown|fdown|aq[a-z0-9]{6,}|snapinsta)",
        s,
        re.IGNORECASE,
    ):
        return True
    # Pure digits / underscores / punctuation / random IDs with no real Arabic or English words
    alnum = re.sub(r"[^A-Za-z\u0600-\u06FF]", "", s)
    if len(alnum) < 3:
        return True
    if re.fullmatch(r"[A-Za-z0-9_\-]{8,}", s) and sum(c.isdigit() for c in s) >= 4:
        return True
    return False


def sanitize_windows_filename(name: str, max_len: int = 62) -> str:
    clean = re.sub(r"[#_]+", " ", str(name or ""))
    clean = re.sub(r'[<>:"/\\|?*\r\n\t]+', " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip(" ._-")
    if len(clean) > max_len:
        cut = clean[:max_len].rsplit(" ", 1)[0].strip(" ._-")
        clean = cut if len(cut) >= 12 else clean[:max_len].strip(" ._-")
    return clean


def build_realistic_video_name(settings: dict[str, Any], timeline: dict[str, Any], brand: dict[str, Any]) -> str:
    """Create a realistic, video-matched Arabic/English filename when the source has no real name."""
    candidates: list[str] = []

    raw_title = str(settings.get("title") or "").strip()
    hook_title = str(settings.get("hookTitle") or "").strip()
    auto_hook = str(timeline.get("auto_hook") or "").strip()
    full_text = str(timeline.get("full_text") or "").strip()

    # 1. If user gave a real non-generic title or hook, prefer it
    if not is_generic_video_name(hook_title):
        candidates.append(hook_title)
    if not is_generic_video_name(raw_title):
        candidates.append(raw_title)

    # 2. Spoken phrase from Whisper transcription (directly describes the actual video!)
    if not is_generic_video_name(auto_hook):
        candidates.append(auto_hook)
    if full_text:
        words = [w.strip(".,،!؟?\"'()[]") for w in full_text.split() if w.strip(".,،!؟?\"'()[]")]
        if len(words) >= 2:
            phrase = " ".join(words[:7])
            if not is_generic_video_name(phrase):
                candidates.append(phrase)

    # 3. Custom text overlay added by the user on the video
    for ov in (settings.get("overlays") or []):
        if isinstance(ov, dict) and ov.get("mode") == "replace":
            ov_txt = " ".join((ov.get("text") or "").splitlines()).strip()
            if not is_generic_video_name(ov_txt):
                candidates.append(ov_txt)
                break

    for cand in candidates:
        safe = sanitize_windows_filename(cand)
        if safe and not is_generic_video_name(safe):
            return safe

    # 4. Graceful realistic fallback with account name + date/time
    import datetime
    acct = sanitize_windows_filename(brand.get("accountName") or "غناوي هلنا", 28) or "غناوي هلنا"
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
    return f"{acct} - مقطع {stamp}"


def auto_export_to_folder(output_mp4: str, settings: dict[str, Any], timeline: dict[str, Any], brand: dict[str, Any], project_dir: str) -> str:
    """Automatically save the final rendered MP4 into the configured export folder (default: D:\\غناوي هلنا)."""
    export_dir = str(brand.get("defaults", {}).get("exportFolder") or r"D:\غناوي هلنا").strip()
    if not export_dir or not os.path.exists(output_mp4):
        return ""
    try:
        os.makedirs(export_dir, exist_ok=True)
        base_name = build_realistic_video_name(settings, timeline, brand)
        dest_path = os.path.join(export_dir, f"{base_name}.mp4")

        # Update project title & exportFileName so UI shows the realistic name everywhere
        if is_generic_video_name(str(settings.get("title") or "")):
            settings["title"] = base_name
        settings["exportFileName"] = f"{base_name}.mp4"
        settings["lastExportPath"] = dest_path
        try:
            with open(os.path.join(project_dir, "settings.json"), "w", encoding="utf-8") as sf:
                json.dump(settings, sf, ensure_ascii=False, indent=2)
        except Exception:
            pass

        shutil.copy2(output_mp4, dest_path)
        print(f"💾 تم الحفظ تلقائياً في: {dest_path}", flush=True)
        return dest_path
    except Exception as exc:
        print(f"⚠️ تعذّر الحفظ التلقائي في {export_dir}: {exc}", flush=True)
        return ""


def generate_post_txt(project_dir: str, brand: dict[str, Any], settings: dict[str, Any], timeline: dict[str, Any]) -> None:
    title = settings.get("hookTitle") or timeline.get("auto_hook") or settings.get("title") or "فيديو جديد"
    full_text = (timeline.get("full_text") or "").strip()
    cta = settings.get("ctaText") or brand.get("cta") or "تابعني ومش هتندم"
    niche = brand.get("niche") or "محتوى عربي وتراث"
    account_name = brand.get("accountName") or ""
    hashtags = (brand.get("hashtags") or "").strip() or "#ريلز #تيك_توك #صناعة_المحتوى #مونتاج #محتوى_عربي #Reels #TikTok #Shorts"

    hook_1 = title
    hook_2 = f"سر مهم عن: {title}"
    hook_3 = f"لو لسه بتعمل كده غلط… شوف {title}"

    excerpt = (full_text[:240] + "...") if len(full_text) > 240 else full_text
    caption_body = excerpt if excerpt else f"ملخص سريع وعملي في أقل من دقيقة حول {title}."

    brand_line = f"الصفحة: {account_name}\n" if account_name else ""
    post_content = f"""==============================
🔥 3 مقترحات لعنوان الفيديو (Hooks)
==============================
1. {hook_1}
2. {hook_2}
3. {hook_3}

==============================
📝 الكابشن الجاهز للنشر
==============================
{hook_1} 👇

{caption_body}

{cta}

==============================
#️⃣ هاشتاجات مقترحة
==============================
{hashtags}
{brand_line}(المجال: {niche})
"""
    with open(os.path.join(project_dir, "post.txt"), "w", encoding="utf-8") as f:
        f.write(post_content)


def render_cover_png(cover_dir: str, dest_png: str) -> bool:
    res = run_cmd([*resolve_hf_cmd(), "snapshot", "--at", "0"], cwd=cover_dir, capture=True)
    if res.returncode != 0:
        print(f"⚠️ تعذّر رندر الغلاف: {res.stderr[:200]}", flush=True)
        return False
    snap_glob = os.path.join(cover_dir, ".hyperframes", "artifacts", "snapshots", "*", "frame-*.png")
    matches = sorted(glob.glob(snap_glob), key=os.path.getmtime, reverse=True)
    if matches:
        shutil.copy2(matches[0], dest_png)
        return True
    return False


def compute_geometry_signatures(settings: dict[str, Any]) -> dict[str, str]:
    """Return stable hashes for visual framing/crop and timeline trim/cut settings."""
    crop_payload = {
        "fitMode": str(settings.get("fitMode", "cover") or "cover"),
        "cropZoom": round(float(settings.get("cropZoom", 1.0) or 1.0), 4),
        "cropPanX": round(float(settings.get("cropPanX", 0.0) or 0.0), 4),
        "cropPanY": round(float(settings.get("cropPanY", 0.0) or 0.0), 4),
        "cropTop": round(float(settings.get("cropTop", 0.0) or 0.0), 4),
        "cropBottom": round(float(settings.get("cropBottom", 0.0) or 0.0), 4),
        "cropLeft": round(float(settings.get("cropLeft", 0.0) or 0.0), 4),
        "cropRight": round(float(settings.get("cropRight", 0.0) or 0.0), 4),
        "verticalCrop": bool(settings.get("verticalCrop", True)),
        "colorPreset": str(settings.get("colorPreset", "warm_creator") or "warm_creator"),
        "lutFile": str(settings.get("lutFile", "") or ""),
        "autoSmartCrop": bool(settings.get("autoSmartCrop", True)),
    }
    time_payload = {
        "trimStart": round(float(settings.get("trimStart", 0.0) or 0.0), 3),
        "trimEnd": round(float(settings.get("trimEnd", 0.0) or 0.0), 3),
        "cutSegments": settings.get("cutSegments") or [],
        "autoCutSilences": bool(settings.get("autoCutSilences", True)),
        "minSilence": round(float(settings.get("minSilence", 0.4) or 0.4), 3),
        "cutPad": round(float(settings.get("cutPad", 0.1) or 0.1), 3),
        "teaserHookEnabled": bool(settings.get("teaserHookEnabled", True)),
        "teaserMode": str(settings.get("teaserMode", "auto") or "auto"),
        "teaserStart": round(float(settings.get("teaserStart", 0.0) or 0.0), 3),
        "teaserDuration": round(float(settings.get("teaserDuration", 3.0) or 3.0), 3),
    }
    crop_sig = hashlib.sha1(json.dumps(crop_payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    time_sig = hashlib.sha1(json.dumps(time_payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return {"crop_sig": crop_sig, "time_sig": time_sig}


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous 1-click AI video editing pipeline.")
    parser.add_argument("project_dir", help="Path to video project directory (e.g. videos/01-first-video)")
    parser.add_argument("--mode", choices=["full", "rerender", "prep"], default="full")
    args = parser.parse_args()

    project_dir = os.path.abspath(args.project_dir)
    work_dir = os.path.join(project_dir, "work")
    os.makedirs(work_dir, exist_ok=True)

    brand_path = os.path.join(ROOT_DIR, "studio", "brand-config.json")
    settings_path = os.path.join(project_dir, "settings.json")
    with open(brand_path, "r", encoding="utf-8-sig") as f:
        brand = json.load(f)
    if os.path.exists(settings_path):
        with open(settings_path, "r", encoding="utf-8-sig") as f:
            settings = json.load(f)
    else:
        settings = {}
    global ENGLISH_FIXES
    ENGLISH_FIXES = {str(k): str(v) for k, v in (settings.get("englishFixes") or {}).items() if str(k).strip()}
    effective_brand = build_hyperframes.resolve_brand_profile(brand, settings)

    input_mp4 = os.path.join(project_dir, "input.mp4")
    trimmed_mp4 = os.path.join(work_dir, "trimmed.mp4")
    safe_input_mp4 = os.path.join(work_dir, "input_with_audio.mp4")
    mastered_mp4 = os.path.join(work_dir, "mastered.mp4")
    graded_mp4 = os.path.join(work_dir, "graded.mp4")
    cut_body_mp4 = os.path.join(work_dir, "cut_body.mp4")
    cut_mp4 = os.path.join(work_dir, "cut.mp4")
    clean_stage_mp4 = os.path.join(work_dir, "clean_stage.mp4")
    rendered_hf_mp4 = os.path.join(work_dir, "rendered_hf.mp4")
    output_mp4 = os.path.join(project_dir, "output.mp4")
    cover_png = os.path.join(project_dir, "cover.png")
    timeline_path = os.path.join(work_dir, "timeline_data.json")
    geom_sig_path = os.path.join(work_dir, "geometry_sig.json")
    visual_sig_path = os.path.join(work_dir, "visual_sig.json")
    cover_sig_path = os.path.join(work_dir, "cover_sig.json")
    audio_sig_path = os.path.join(work_dir, "audio_master_sig.json")
    cur_audio_sig = compute_audio_master_sig(settings)

    if not os.path.exists(input_mp4):
        print("❌ ملف input.mp4 غير موجود داخل فولدر المشروع!", file=sys.stderr)
        sys.exit(1)

    # Clean any stale failed HyperFrames transaction directories from previous runs
    for stale_tx in glob.glob(os.path.join(work_dir, ".rendered_hf.hf-transaction-*")):
        shutil.rmtree(stale_tx, ignore_errors=True)

    cur_geom = compute_geometry_signatures(settings)
    saved_geom: dict[str, Any] = {}
    if os.path.exists(geom_sig_path):
        try:
            with open(geom_sig_path, "r", encoding="utf-8-sig") as gf:
                saved_geom = json.load(gf)
        except Exception:
            saved_geom = {}

    effective_mode = args.mode
    if effective_mode == "rerender":
        if not os.path.exists(cut_mp4) or not os.path.exists(timeline_path):
            print("ℹ️ ملفات المونتاج الأساسية غير مكتملة — جاري تشغيل البايبلاين الكامل تلقائياً...", flush=True)
            effective_mode = "full"
        elif saved_geom and saved_geom.get("time_sig") != cur_geom["time_sig"]:
            print("✂️ تم تعديل قصّ المدة أو الأجزاء المحذوفة — جاري إعادة بناء الفيديو بالكامل لضمان الدقة...", flush=True)
            effective_mode = "full"
        elif not saved_geom and (
            float(settings.get("trimStart", 0) or 0) > 0
            or float(settings.get("trimEnd", 0) or 0) > 0
            or bool(settings.get("cutSegments"))
        ):
            print("✂️ جاري تطبيق قصّ المدة المحدد وإعادة بناء الفيديو بالكامل...", flush=True)
            effective_mode = "full"

    if effective_mode in ("full", "prep"):
        # --- STAGE 1: OPTIONAL TRIM + AUDIO MASTERING ---
        emit_stage(1, 6, 10, "قصّ البداية/النهاية ومعالجة الصوت (-14 LUFS)...")
        src_trimmed = trim_input_video(
            input_mp4,
            trimmed_mp4,
            float(settings.get("trimStart", 0) or 0),
            float(settings.get("trimEnd", 0) or 0),
            settings.get("cutSegments") or [],
        )
        has_real_audio = ensure_audio_stream(src_trimmed, safe_input_mp4)
        audio_src = src_trimmed if has_real_audio else safe_input_mp4

        denoise = settings.get("denoise", "light")
        lufs = str(settings.get("lufs", -14))
        voice_preset = settings.get("voicePreset", "studio")
        res = run_cmd([
            sys.executable, os.path.join(SCRIPTS_DIR, "master_audio.py"),
            audio_src, mastered_mp4,
            "--denoise", denoise,
            "--preset", voice_preset,
            "--lufs", lufs,
        ])
        if res.returncode != 0:
            sys.exit(res.returncode)

        # --- STAGE 2: SMART AUTO-CROP + COLOR GRADING & VISUAL 9:16 REFRAME ---
        emit_stage(2, 6, 25, "فحص القصّ الذكي وتصحيح الألوان وتظبيط الكادر 1080×1920...")
        c_top = float(settings.get("cropTop", 0.0) or 0.0)
        c_bot = float(settings.get("cropBottom", 0.0) or 0.0)
        c_left = float(settings.get("cropLeft", 0.0) or 0.0)
        c_right = float(settings.get("cropRight", 0.0) or 0.0)
        manual_crop = any(v > 0.0 for v in (c_top, c_bot, c_left, c_right))
        if not manual_crop and settings.get("autoSmartCrop", True):
            try:
                detected = smart_crop.detect_smart_crop(mastered_mp4)
                c_top = detected["cropTop"]
                c_bot = detected["cropBottom"]
                c_left = detected["cropLeft"]
                c_right = detected["cropRight"]
                if any(v > 0.0 for v in (c_top, c_bot, c_left, c_right)):
                    print(
                        f"🤖 القصّ الذكي التلقائي: أعلى {c_top}% · أسفل {c_bot}% · يسار {c_left}% · يمين {c_right}%",
                        flush=True,
                    )
            except Exception as exc:
                print(f"ℹ️ تخطّي القصّ الذكي: {exc}", flush=True)

        color_cmd = [
            sys.executable, os.path.join(SCRIPTS_DIR, "color_grade.py"),
            mastered_mp4, graded_mp4,
            "--fast", "--crf", "16",
            "--fit-mode", settings.get("fitMode", "cover"),
            "--zoom", str(settings.get("cropZoom", 1.0)),
            "--pan-x", str(settings.get("cropPanX", 0.0)),
            "--pan-y", str(settings.get("cropPanY", 0.0)),
            "--crop-top", str(c_top),
            "--crop-bottom", str(c_bot),
            "--crop-left", str(c_left),
            "--crop-right", str(c_right),
        ]
        lut_file = settings.get("lutFile", "")
        lut_full = os.path.join(ROOT_DIR, "assets", "luts", lut_file) if lut_file else ""
        if lut_file and os.path.exists(lut_full):
            color_cmd.extend(["--lut", lut_full])
        else:
            color_cmd.extend(["--preset", settings.get("colorPreset", "warm_creator")])
        if settings.get("verticalCrop", True):
            color_cmd.append("--vertical")
        res = run_cmd(color_cmd)
        if res.returncode != 0:
            sys.exit(res.returncode)

        if effective_mode == "prep":
            emit_stage(6, 6, 100, "اكتملت معالجة الصوت والألوان بنجاح!")
            return

        # --- STAGE 3: WHISPER TRANSCRIPTION ---
        emit_stage(3, 6, 42, "تفريغ الكلام بالذكاء الاصطناعي (Whisper)...")
        words: list[dict[str, Any]] = []
        if has_real_audio and settings.get("whisperEnabled", True):
            model = settings.get("whisperModel", "small")
            lang = settings.get("language", brand.get("language", "ar"))
            words = transcribe_with_hyperframes(graded_mp4, work_dir, model, lang)
            print(f"📝 تم تفريغ {len(words)} كلمة.", flush=True)
        else:
            print("ℹ️ تخطّي التفريغ الصوتي (الفيديو بدون كلام أو Whisper مغلق).", flush=True)

        # --- STAGE 4: GLOSSARY + SMART SILENCE CUTS + 3s TEASER HOOK ---
        emit_stage(4, 6, 56, "تطبيق القاموس وقصّ السكوت وتجهيز هوك الـ 3 ثواني...")
        glossary = load_combined_glossary(brand)
        # per-run corrections (settings_json: {"glossaryExtra": {"wrong": "right"}}), not saved globally
        for _w, _r in (settings.get("glossaryExtra") or {}).items():
            if str(_w).strip() and str(_r).strip():
                glossary[str(_w).strip()] = str(_r).strip()
        words = clean_transcript.apply_glossary(words, glossary)

        graded_info = probe_media(graded_mp4)
        orig_dur = graded_info["duration"]
        min_sil = float(settings.get("minSilence", 0.4))
        cut_pad = float(settings.get("cutPad", 0.1))

        if has_real_audio and settings.get("autoCutSilences", True):
            silences = detect_silences_ffmpeg(graded_mp4, min_sil)
            keeps = compute_keep_segments(orig_dur, silences, cut_pad)
        else:
            keeps = [(0.0, orig_dur)]

        cut_video_by_segments(graded_mp4, cut_body_mp4, keeps, orig_dur)
        body_dur = probe_media(cut_body_mp4)["duration"]
        saved_sec = max(0.0, round(orig_dur - body_dur, 2))
        print(f"✂️ مدة الفيديو بعد القصّ الذكي: {body_dur:.2f}s (وفّرنا {saved_sec:.2f}s من السكوت).", flush=True)

        # Remap word timestamps onto cut_body timeline
        remapped_words = []
        for w in words:
            ns = remap_time(w["start"], keeps)
            ne = remap_time(w["end"], keeps)
            if ne <= ns:
                ne = round(ns + 0.15, 3)
            remapped_words.append({"word": w["word"], "start": ns, "end": min(body_dur, ne)})

        cut_points: list[float] = []
        acc_t = 0.0
        for idx_k, (ks, ke) in enumerate(keeps):
            acc_t += (ke - ks)
            if idx_k < len(keeps) - 1 and 0.4 < acc_t < body_dur - 0.5:
                cut_points.append(round(acc_t, 3))

        # Optional 3-Second Viral Teaser Hook at start of video
        applied_teaser_dur = 0.0
        teaser_src_start = 0.0
        teaser_badge = (settings.get("teaserBadge") or "شاهد للنهاية 🔥").strip()
        if settings.get("teaserHookEnabled", True) and body_dur >= 5.0:
            req_dur = max(2.0, min(4.5, float(settings.get("teaserDuration", 3.0) or 3.0)))
            if settings.get("teaserMode", "auto") == "manual":
                teaser_src_start = max(0.0, min(body_dur - req_dur, float(settings.get("teaserStart", 0.0) or 0.0)))
            else:
                teaser_src_start = find_best_teaser_start(cut_body_mp4, body_dur, req_dur)

            if prepend_teaser_hook(cut_body_mp4, cut_mp4, teaser_src_start, req_dur):
                applied_teaser_dur = req_dur
                print(
                    f"🔥 تم تركيب هوك تشويقي ({applied_teaser_dur:.1f}s) من الثانية {teaser_src_start:.2f}s في أول الفيديو.",
                    flush=True,
                )
            else:
                shutil.copy2(cut_body_mp4, cut_mp4)
        else:
            shutil.copy2(cut_body_mp4, cut_mp4)

        new_dur = probe_media(cut_mp4)["duration"]
        if applied_teaser_dur > 0:
            remapped_words = [
                {
                    "word": w["word"],
                    "start": round(w["start"] + applied_teaser_dur, 3),
                    "end": round(min(new_dur, w["end"] + applied_teaser_dur), 3),
                }
                for w in remapped_words
            ]
            cut_points = [round(applied_teaser_dur, 3)] + [
                round(cp + applied_teaser_dur, 3) for cp in cut_points
            ]

        max_words = 1 if settings.get("captionStyle") == "word_by_word" else int(settings.get("maxWords", 4))
        chunks = clean_transcript.build_chunks(remapped_words, max_words=max_words)
        captions = [
            {
                "id": i,
                "start": ch["start"],
                "end": ch["end"],
                "text": ch["text"],
                "en_text": "",
                "highlight": "",
                "broll": "",
                "zoom": False,
                "words": ch.get("words", []),
            }
            for i, ch in enumerate(chunks)
        ]

        if settings.get("bilingualCaptions", True) and captions:
            populate_bilingual_captions(captions, settings.get("language", brand.get("language", "ar")))

        full_text = " ".join(w["word"] for w in remapped_words).strip()
        auto_hook = ""
        if captions:
            # Extract first meaningful phrase from the speech as viral hook
            first_chunks = captions[:3]
            speech_tokens = [w["word"] for c in first_chunks for w in c.get("words", [])]
            picked_words = []
            for tok in speech_tokens:
                clean_tok = tok.strip()
                picked_words.append(clean_tok.strip(".,،!؟?"))
                if len(picked_words) >= 6 or clean_tok.endswith((".", "!", "؟", "?")):
                    break
            if picked_words:
                auto_hook = " ".join(picked_words)

        if not auto_hook and captions:
            first_words = " ".join(c["text"] for c in captions[:2]).split()
            auto_hook = " ".join(first_words[:6])

        # Speech too short (music / no talking) -> clear auto_hook so we don't show a 1-word artifact
        if len(auto_hook.split()) < 2:
            auto_hook = ""

        # Derive a realistic video-matched title (speech -> meaningful video/URL title -> custom overlay)
        raw_title = str(settings.get("title") or "").strip()
        is_generic_title = is_generic_video_name(raw_title)
        clean_video_title = "" if is_generic_title else sanitize_windows_filename(raw_title, 70)

        if not settings.get("hookTitle"):
            if auto_hook:
                settings["hookTitle"] = auto_hook
            elif clean_video_title:
                settings["hookTitle"] = clean_video_title
            else:
                settings["hookTitle"] = ""

        if is_generic_title:
            smart_title = build_realistic_video_name(settings, {"auto_hook": auto_hook, "full_text": full_text}, effective_brand)
            if smart_title:
                settings["title"] = smart_title

        # Persist updated title/hookTitle in settings.json
        try:
            with open(os.path.join(project_dir, "settings.json"), "w", encoding="utf-8") as sf:
                json.dump(settings, sf, ensure_ascii=False, indent=2)
        except Exception:
            pass

        timeline_data = {
            "duration": round(new_dur, 3),
            "original_duration": round(orig_dur, 3),
            "saved_seconds": saved_sec,
            "teaser_duration": applied_teaser_dur,
            "teaser_source_start": teaser_src_start,
            "teaser_badge": teaser_badge,
            "keep_segments": keeps,
            "cut_points": cut_points,
            "auto_hook": auto_hook,
            "full_text": full_text,
            "captions": captions,
        }
        with open(timeline_path, "w", encoding="utf-8") as f:
            json.dump(timeline_data, f, ensure_ascii=False, indent=2)
        with open(geom_sig_path, "w", encoding="utf-8") as gf:
            json.dump(cur_geom, gf, ensure_ascii=False, indent=2)
        with open(audio_sig_path, "w", encoding="utf-8") as af:
            json.dump({"audio_sig": cur_audio_sig}, af, ensure_ascii=False, indent=2)
    else:
        # Rerender mode: load existing timeline_data.json & verify crop/zoom geometry matches cut.mp4!
        if os.path.exists(timeline_path):
            with open(timeline_path, "r", encoding="utf-8-sig") as f:
                timeline_data = json.load(f)
            if settings.get("bilingualCaptions", True) and timeline_data.get("captions"):
                before_cnt = sum(1 for c in timeline_data["captions"] if (c.get("en_text") or "").strip())
                populate_bilingual_captions(timeline_data["captions"], settings.get("language", brand.get("language", "ar")))
                after_cnt = sum(1 for c in timeline_data["captions"] if (c.get("en_text") or "").strip())
                if after_cnt > before_cnt:
                    with open(timeline_path, "w", encoding="utf-8") as f:
                        json.dump(timeline_data, f, ensure_ascii=False, indent=2)
        else:
            dur = probe_media(cut_mp4)["duration"]
            timeline_data = {"duration": dur, "captions": [], "full_text": "", "auto_hook": ""}

        # CRITICAL: If crop/zoom/fitMode changed (or geometry_sig.json missing), ALWAYS re-apply real FFmpeg crop to cut.mp4!
        if saved_geom.get("crop_sig") != cur_geom["crop_sig"]:
            emit_stage(2, 6, 28, "تطبيق القصّ والزوم الجديد على الفيديو بدقة 100% (مع الحفاظ على الترجمة)...")
            src_trimmed = trim_input_video(
                input_mp4,
                trimmed_mp4,
                float(settings.get("trimStart", 0) or 0),
                float(settings.get("trimEnd", 0) or 0),
                settings.get("cutSegments") or [],
            )
            has_real_audio = ensure_audio_stream(src_trimmed, safe_input_mp4)
            audio_src = src_trimmed if has_real_audio else safe_input_mp4
            m_res = run_cmd([
                sys.executable, os.path.join(SCRIPTS_DIR, "master_audio.py"),
                audio_src, mastered_mp4,
                "--denoise", settings.get("denoise", "light"),
                "--preset", settings.get("voicePreset", "studio"),
                "--lufs", str(settings.get("lufs", -14)),
            ])
            grade_src = mastered_mp4 if (m_res.returncode == 0 and os.path.exists(mastered_mp4)) else audio_src

            c_top = float(settings.get("cropTop", 0.0) or 0.0)
            c_bot = float(settings.get("cropBottom", 0.0) or 0.0)
            c_left = float(settings.get("cropLeft", 0.0) or 0.0)
            c_right = float(settings.get("cropRight", 0.0) or 0.0)
            manual_crop = any(v > 0.0 for v in (c_top, c_bot, c_left, c_right))
            if not manual_crop and settings.get("autoSmartCrop", True):
                try:
                    detected = smart_crop.detect_smart_crop(grade_src)
                    c_top = detected["cropTop"]
                    c_bot = detected["cropBottom"]
                    c_left = detected["cropLeft"]
                    c_right = detected["cropRight"]
                except Exception:
                    pass

            color_cmd = [
                sys.executable, os.path.join(SCRIPTS_DIR, "color_grade.py"),
                grade_src, graded_mp4,
                "--fast", "--crf", "16",
                "--fit-mode", settings.get("fitMode", "cover"),
                "--zoom", str(settings.get("cropZoom", 1.0)),
                "--pan-x", str(settings.get("cropPanX", 0.0)),
                "--pan-y", str(settings.get("cropPanY", 0.0)),
                "--crop-top", str(c_top),
                "--crop-bottom", str(c_bot),
                "--crop-left", str(c_left),
                "--crop-right", str(c_right),
            ]
            lut_file = settings.get("lutFile", "")
            lut_full = os.path.join(ROOT_DIR, "assets", "luts", lut_file) if lut_file else ""
            if lut_file and os.path.exists(lut_full):
                color_cmd.extend(["--lut", lut_full])
            else:
                color_cmd.extend(["--preset", settings.get("colorPreset", "warm_creator")])
            if settings.get("verticalCrop", True):
                color_cmd.append("--vertical")
            g_res = run_cmd(color_cmd)
            if g_res.returncode != 0:
                sys.exit(g_res.returncode)

            graded_dur = probe_media(graded_mp4)["duration"]
            keeps_saved = [
                (float(seg[0]), float(seg[1]))
                for seg in (timeline_data.get("keep_segments") or [])
                if isinstance(seg, (list, tuple)) and len(seg) == 2 and float(seg[1]) > float(seg[0])
            ]
            if keeps_saved:
                cut_video_by_segments(graded_mp4, cut_body_mp4, keeps_saved, graded_dur)
            else:
                shutil.copy2(graded_mp4, cut_body_mp4)

            t_dur = float(timeline_data.get("teaser_duration") or 0.0)
            t_start = float(timeline_data.get("teaser_source_start") or 0.0)
            if t_dur > 0.5 and prepend_teaser_hook(cut_body_mp4, cut_mp4, t_start, t_dur):
                pass
            else:
                shutil.copy2(cut_body_mp4, cut_mp4)

            with open(geom_sig_path, "w", encoding="utf-8") as gf:
                json.dump(cur_geom, gf, ensure_ascii=False, indent=2)
            with open(audio_sig_path, "w", encoding="utf-8") as af:
                json.dump({"audio_sig": cur_audio_sig}, af, ensure_ascii=False, indent=2)

    # --- STAGE 5: DELOGO MASKS + BUILD & RENDER HYPERFRAMES + COVER THUMBNAIL ---
    emit_stage(5, 6, 72, "تطبيق مسح اللوجو وبناء مشاهد HyperFrames والترجمة والعناوين...")
    stage_video = apply_delogo_masks(cut_mp4, clean_stage_mp4, settings.get("overlays") or [])
    build_info = build_hyperframes.build_project(ROOT_DIR, project_dir, brand, settings, timeline_data, stage_video)
    print(
        f"🎨 تم بناء المشروع ({build_info['caption_count']} سطر ترجمة · "
        f"{build_info['callout_count']} كارت توضيحي · {build_info['broll_count']} ملف B-Roll).",
        flush=True,
    )

    quality = settings.get("renderQuality", "standard")
    saved_vis: dict[str, Any] = {}
    if os.path.exists(visual_sig_path):
        try:
            with open(visual_sig_path, "r", encoding="utf-8-sig") as vf:
                saved_vis = json.load(vf)
        except Exception:
            saved_vis = {}

    # Clear stale .hyperframes segment cache ONLY if the underlying cropped video changed
    if saved_vis.get("source_video_name") and saved_vis.get("source_video_name") != build_info.get("source_video_name"):
        shutil.rmtree(os.path.join(build_info["hf_dir"], ".hyperframes"), ignore_errors=True)

    # TIER 1 INSTANT RERENDER: If visuals didn't change (only music/voice/SFX/post changed), reuse cached rendered_hf.mp4!
    can_reuse_visual_render = (
        os.path.exists(rendered_hf_mp4)
        and saved_vis.get("visual_sig") == build_info.get("visual_sig")
        and saved_vis.get("quality") == quality
    )
    if can_reuse_visual_render:
        emit_stage(5, 6, 86, "⚡ المشهد البصري جاهز مسبقاً — تخطّي الرندر البصري والانتقال الفوري للصوت والموسيقى!")
        print("⚡ [Smart Cache HIT] تخطّي رندر HyperFrames بالكامل — المشهد البصري مطابق للرندرة السابقة.", flush=True)
    else:
        hf_bin = resolve_hf_cmd()
        workers = optimal_render_workers()
        base_render_args = [
            *hf_bin, "render",
            "--quality", quality,
            "--workers", str(workers),
            "--browser-gpu",
            "--resume",
            "--keep-segments",
            "-o", rendered_hf_mp4,
        ]
        print(f"🚀 تشغيل الرندر المسرّع: {workers} workers · Hardware GPU · Segment Cache", flush=True)
        render_res = run_cmd([*base_render_args[:-2], "--gpu", "-o", rendered_hf_mp4], cwd=build_info["hf_dir"])
        if render_res.returncode != 0 or not os.path.exists(rendered_hf_mp4):
            print("⚠️ تعذّر الترميز بـ GPU — جاري المتابعة بترميز CPU متعدد الأنوية...", flush=True)
            render_res = run_cmd(base_render_args, cwd=build_info["hf_dir"])
        if render_res.returncode != 0 or not os.path.exists(rendered_hf_mp4):
            print("❌ فشل رندر HyperFrames.", file=sys.stderr)
            sys.exit(render_res.returncode or 1)
        with open(visual_sig_path, "w", encoding="utf-8") as vf:
            json.dump(
                {
                    "visual_sig": build_info.get("visual_sig"),
                    "source_video_name": build_info.get("source_video_name"),
                    "quality": quality,
                },
                vf,
                ensure_ascii=False,
                indent=2,
            )

    # Smart Cover Cache: Skip Chrome cover snapshot when cover.png already matches current title & video!
    saved_cover: dict[str, Any] = {}
    if os.path.exists(cover_sig_path):
        try:
            with open(cover_sig_path, "r", encoding="utf-8-sig") as cf:
                saved_cover = json.load(cf)
        except Exception:
            saved_cover = {}
    if os.path.exists(cover_png) and saved_cover.get("cover_sig") == build_info.get("cover_sig"):
        print("⚡ [Smart Cache HIT] صورة الغلاف (cover.png) جاهزة مسبقاً ولم تتغيّر.", flush=True)
    else:
        print("🖼️ جاري تصميم وتصدير صورة الغلاف (cover.png)...", flush=True)
        if render_cover_png(build_info["cover_dir"], cover_png):
            with open(cover_sig_path, "w", encoding="utf-8") as cf:
                json.dump({"cover_sig": build_info.get("cover_sig")}, cf, ensure_ascii=False, indent=2)

    # --- STAGE 6: VOICEOVER / VOICE FX + AUTO-DUCKING MUSIC + SFX MIX + POST.TXT ---
    emit_stage(6, 6, 90, "معالجة الصوت ودمج الموسيقى والمؤثرات وتجهيز كابشن النشر...")
    music_file = settings.get("musicFile", "")
    music_dir = os.path.join(ROOT_DIR, "assets", "music")
    music_path = ""
    if music_file and os.path.exists(os.path.join(music_dir, music_file)):
        music_path = os.path.join(music_dir, music_file)
    elif (not music_file or music_file == "auto") and os.path.exists(music_dir):
        tracks = [f for f in os.listdir(music_dir) if f.lower().endswith((".mp3", ".wav", ".m4a")) and not f.startswith(".")]
        if tracks and settings.get("musicDb", -23) > -80:
            music_path = os.path.join(music_dir, tracks[0])

    # Optional Voice FX re-mastering ONLY when audio settings actually changed since cut.mp4 was mastered!
    mix_input_video = rendered_hf_mp4
    audio_source = settings.get("audioSource", "original")
    mute_original = bool(settings.get("muteOriginal", False))
    voice_preset = settings.get("voicePreset", "studio")
    denoise_lvl = settings.get("denoise", "light")

    saved_audio_sig = ""
    if os.path.exists(audio_sig_path):
        try:
            with open(audio_sig_path, "r", encoding="utf-8-sig") as af:
                saved_audio_sig = json.load(af).get("audio_sig", "")
        except Exception:
            saved_audio_sig = ""

    if effective_mode == "rerender" and not mute_original and voice_preset != "raw" and saved_audio_sig != cur_audio_sig:
        remastered_hf = os.path.join(work_dir, "rerender_mastered.mp4")
        m_res = run_cmd([
            sys.executable, os.path.join(SCRIPTS_DIR, "master_audio.py"),
            rendered_hf_mp4, remastered_hf,
            "--denoise", denoise_lvl,
            "--preset", voice_preset,
            "--lufs", str(settings.get("lufs", -14)),
        ])
        if m_res.returncode == 0 and os.path.exists(remastered_hf):
            mix_input_video = remastered_hf

    # Resolve external voice track (uploaded custom audio or AI TTS)
    voice_track_path = ""
    if audio_source == "custom":
        raw_custom = os.path.join(work_dir, "custom_voice_raw")
        candidates = glob.glob(os.path.join(work_dir, "custom_voice_raw.*"))
        mastered_custom = os.path.join(work_dir, "custom_voice.wav")
        if candidates:
            src_custom = candidates[0]
            cm_res = run_cmd([
                sys.executable, os.path.join(SCRIPTS_DIR, "master_audio.py"),
                src_custom, mastered_custom,
                "--denoise", denoise_lvl,
                "--preset", voice_preset,
                "--audio-only",
            ])
            if cm_res.returncode == 0 and os.path.exists(mastered_custom):
                voice_track_path = mastered_custom
        elif os.path.exists(mastered_custom):
            voice_track_path = mastered_custom
    elif audio_source == "tts":
        tts_wav = os.path.join(work_dir, "tts_voice.wav")
        if os.path.exists(tts_wav):
            voice_track_path = tts_wav

    # Merge auto SFX cues + user custom SFX cues
    sfx_enabled = settings.get("sfxEnabled", True)
    cues_path = build_info["sfx_cues_path"]
    merged_cues: list[dict[str, Any]] = []
    if sfx_enabled and os.path.exists(cues_path):
        try:
            with open(cues_path, "r", encoding="utf-8-sig") as cf:
                merged_cues = json.load(cf)
        except Exception:
            merged_cues = []

    sfx_dir = os.path.join(ROOT_DIR, "assets", "sfx")
    for cs in (settings.get("customSfx") or []):
        if not isinstance(cs, dict):
            continue
        fname = os.path.basename(str(cs.get("file") or ""))
        fpath = os.path.join(sfx_dir, fname)
        if fname and os.path.exists(fpath):
            merged_cues.append({
                "file": fpath,
                "time": max(0.0, float(cs.get("time") or 0.0)),
                "volume_db": float(cs.get("volume_db", -10.0)),
            })

    merged_cues_path = os.path.join(work_dir, "merged_sfx_cues.json")
    if merged_cues:
        with open(merged_cues_path, "w", encoding="utf-8") as mf:
            json.dump(merged_cues, mf, ensure_ascii=False, indent=2)

    needs_mix = bool(music_path or merged_cues or voice_track_path or mute_original)
    if needs_mix:
        mix_cmd = [sys.executable, os.path.join(SCRIPTS_DIR, "mix_audio.py"), mix_input_video, output_mp4]
        if music_path:
            mix_cmd.extend(["--music", music_path, "--music-db", str(settings.get("musicDb", -23))])
            if not settings.get("autoDuck", True):
                mix_cmd.append("--no-duck")
        if voice_track_path:
            mix_cmd.extend(["--voice-track", voice_track_path, "--voice-db", str(settings.get("voiceDb", 0.0))])
            if not mute_original:
                mix_cmd.extend(["--original-db", str(settings.get("originalDb", -10.0))])
        if mute_original:
            mix_cmd.append("--mute-original")
        if merged_cues:
            mix_cmd.extend(["--sfx-cues", merged_cues_path])
        mix_res = run_cmd(mix_cmd)
        if mix_res.returncode != 0:
            print("⚠️ فشل دمج الصوت الإضافي — تم حفظ الفيديو المرندر مباشرة.", flush=True)
            shutil.copy2(mix_input_video, output_mp4)
    else:
        shutil.copy2(mix_input_video, output_mp4)

    generate_post_txt(project_dir, effective_brand, settings, timeline_data)
    exported_path = auto_export_to_folder(output_mp4, settings, timeline_data, effective_brand, project_dir)

    # Auto-clean heavy scratch files while KEEPING rendered_hf.mp4 & .hyperframes for blazing-fast 2nd renders!
    temp_files = [
        "trimmed.mp4",
        "mastered.mp4",
        "graded.mp4",
        "cut_body.mp4",
        "clean_stage.mp4",
        "rerender_mastered.mp4",
        "crop_preview.mp4",
        "input_silent.mp4",
    ]
    for tf in temp_files:
        tp = os.path.join(work_dir, tf)
        if os.path.exists(tp):
            try:
                os.remove(tp)
            except OSError:
                pass
    for stale_tx in glob.glob(os.path.join(work_dir, ".rendered_hf.hf-transaction-*")):
        shutil.rmtree(stale_tx, ignore_errors=True)

    done_note = f"✅ اكتمل المونتاج وتم الحفظ في: {exported_path}" if exported_path else "✅ اكتمل المونتاج بالكامل! output.mp4 و cover.png و post.txt جاهزين للنشر."
    emit_stage(6, 6, 100, done_note)


if __name__ == "__main__":
    main()

