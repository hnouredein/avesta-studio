"""
Build a contract-compliant, agency-grade HyperFrames 9:16 vertical composition
and a 4:5-safe Instagram Cover (cover.html) from timeline_data.json + settings.json + brand-config.json.

Pro Features Included:
  1. Karaoke Word-by-Word highlighting synced to Whisper word timestamps (`captionStyle == "karaoke"`).
  2. Opening Whip-Zoom + Light-Leak Flash + Cut-Zoom Alternation on silence cuts.
  3. Deterministic GSAP 7-bar Audio Waveform Visualizer + Smart Step/Topic Pill.
  4. Smart Emoji/Icon Pop-ups triggered by power keywords in Arabic & English.
  5. Persistent subtle Brand Watermark Pill (Logo + Account Name) in the top safe zone.
  6. Per-caption explicit B-Roll & Strong Zoom cues + automatic B-Roll distribution.

All assets (fonts, video, logo, B-Roll) are copied into hf_project/assets/ so rendering is 100% offline.
"""

import argparse
import hashlib
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
from typing import Any


LATIN_RE = re.compile(r"([A-Za-z0-9][A-Za-z0-9@#._+\-/%]*[A-Za-z0-9]|[A-Za-z0-9]+)")
NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?%?")
STOP_WORDS_AR = {
    "في", "من", "على", "إلى", "الى", "عن", "مع", "ده", "دي", "اللي", "اللى", "أن", "ان",
    "إن", "هو", "هي", "احنا", "إحنا", "انت", "أنت", "لو", "بس", "يعني", "كان", "مش", "ما",
    "لا", "كل", "أو", "او", "و", "ب", "ل", "ك", "عشان", "علشان", "زي", "كده", "جدا", "جداً",
    "the", "and", "for", "that", "this", "with", "you", "your", "are", "was", "from", "have",
}

KEYWORD_EMOJIS: list[tuple[tuple[str, ...], str]] = [
    (("مجاني", "مجاناً", "ببلاش", "فري", "free"), "🎁"),
    (("سر", "أسرار", "اسرار", "خفي", "secret"), "🤫"),
    (("تحذير", "غلط", "خطأ", "خطر", "احذر", "warning", "mistake"), "⚠️"),
    (("فلوس", "ربح", "دولار", "جنيه", "سعر", "مكسب", "money"), "💸"),
    (("ثانية", "سريع", "سرعة", "فوراً", "بسرعة", "fast", "second"), "⚡"),
    (("فكرة", "ذكاء", "اصطناعي", "أداة", "اداة", "ai", "smart", "idea"), "💡"),
    (("اشترك", "فولو", "لايك", "نجاح", "انطلق", "صاروخ", "subscribe", "follow"), "🚀"),
]


# key -> (css family, font file, weight range). Keys are what the app sends as arabicFont/hookFont/captionFont.
FONT_REGISTRY = {
    "cairo": ("CairoPro", "Cairo-Variable.ttf", "200 900"),
    "tajawal": ("TajawalPro", "Tajawal-Bold.ttf", "100 900"),
    "amiri": ("AmiriPro", "Amiri-Bold.ttf", "100 900"),
    "changa": ("ChangaPro", "Changa-Variable.ttf", "200 900"),
    "reemkufi": ("ReemKufiPro", "ReemKufi-Variable.ttf", "200 900"),
    "almarai": ("AlmaraiPro", "Almarai-Bold.ttf", "100 900"),
    "lalezar": ("LalezarPro", "Lalezar-Regular.ttf", "100 900"),
    "elmessiri": ("ElMessiriPro", "ElMessiri-Variable.ttf", "400 700"),
    "kufam": ("KufamPro", "Kufam-Variable.ttf", "400 900"),
    "rakkas": ("RakkasPro", "Rakkas-Regular.ttf", "100 900"),
    "lateef": ("LateefPro", "Lateef-Bold.ttf", "100 900"),
    "scheherazade": ("ScheherazadePro", "ScheherazadeNew-Bold.ttf", "100 900"),
    "notokufi": ("NotoKufiPro", "NotoKufiArabic-Variable.ttf", "100 900"),
    "plex": ("PlexArabicPro", "IBMPlexSansArabic-Bold.ttf", "100 900"),
    "readex": ("ReadexPro", "ReadexPro-Variable.ttf", "160 700"),
    "mada": ("MadaPro", "Mada-Variable.ttf", "200 900"),
    "marhey": ("MarheyPro", "Marhey-Variable.ttf", "300 700"),
    "baloo": ("BalooPro", "BalooBhaijaan2-Variable.ttf", "400 800"),
    "arefruqaa": ("ArefRuqaaPro", "ArefRuqaa-Bold.ttf", "100 900"),
    "katibeh": ("KatibehPro", "Katibeh-Regular.ttf", "100 900"),
    "lemonada": ("LemonadaPro", "Lemonada-Variable.ttf", "300 700"),
    "jomhuria": ("JomhuriaPro", "Jomhuria-Regular.ttf", "100 900"),
}


def font_css_name(key, fallback="cairo"):
    k = (key or "").strip().lower()
    return FONT_REGISTRY.get(k, FONT_REGISTRY[fallback])[0]


def font_faces_css(indent="    "):
    out = []
    for fam, fname, wt in FONT_REGISTRY.values():
        out.append(
            f'{indent}@font-face {{ font-family: "{fam}"; src: url("assets/fonts/{fname}") format("truetype"); '
            f'font-weight: {wt}; font-style: normal; font-display: swap; }}'
        )
    return "\n".join(out)



def hex_to_rgba(hex_color: str, alpha: float) -> str:
    clean = (hex_color or "#0C0C10").lstrip("#")
    if len(clean) == 3:
        clean = "".join(c * 2 for c in clean)
    try:
        r = int(clean[0:2], 16)
        g = int(clean[2:4], 16)
        b = int(clean[4:6], 16)
    except Exception:
        r, g, b = 12, 12, 16
    return f"rgba({r}, {g}, {b}, {alpha})"


def detect_keyword_emoji(text: str) -> str:
    low = text.lower()
    for keys, emoji in KEYWORD_EMOJIS:
        for k in keys:
            if k in low:
                return emoji
    return ""


def pick_power_word_index(words: list[str]) -> int:
    if not words:
        return -1
    best_idx = -1
    best_score = -1
    for i, raw in enumerate(words):
        w = raw.strip(".,،!?؟\"'()[]")
        if not w:
            continue
        score = 0
        if NUMBER_RE.search(w):
            score += 50
        if LATIN_RE.fullmatch(w) and len(w) >= 2:
            score += 35
        if w.lower() not in STOP_WORDS_AR:
            score += min(len(w) * 3, 24)
        if score > best_score:
            best_score = score
            best_idx = i
    return best_idx if best_score >= 12 else -1


def format_rtl_html(text: str, highlight_word: str = "") -> str:
    tokens = text.split()
    if not tokens:
        return ""
    hl_idx = -1
    if highlight_word:
        for i, t in enumerate(tokens):
            if highlight_word in t:
                hl_idx = i
                break
    if hl_idx == -1:
        hl_idx = pick_power_word_index(tokens)

    parts = []
    for i, tok in enumerate(tokens):
        escaped = html.escape(tok)
        is_latin = bool(LATIN_RE.fullmatch(tok.strip(".,،!?؟")))
        if i == hl_idx:
            if is_latin:
                parts.append(f'<span class="pw" dir="ltr">{escaped}</span>')
            else:
                parts.append(f'<span class="pw">{escaped}</span>')
        elif is_latin:
            parts.append(f'<span dir="ltr">{escaped}</span>')
        else:
            parts.append(escaped)
    return " ".join(parts)


def extract_cover_frame(video_path: str, out_jpg: str, duration: float) -> bool:
    if not shutil.which("ffmpeg") or not os.path.exists(video_path):
        return False
    seek_t = min(max(0.5, duration * 0.18), max(0.0, duration - 0.3))
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{seek_t:.2f}",
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "2",
        out_jpg,
    ]
    res = subprocess.run(cmd, capture_output=True)
    return res.returncode == 0 and os.path.exists(out_jpg)


def resolve_brand_profile(brand: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    """Merge the active brand profile ('ghinawi_halna' by default or 'egyptian_identity') into brand config."""
    profile_id = (settings.get("brandProfile") or brand.get("defaultProfileId") or "ghinawi_halna").strip()
    profiles = brand.get("profiles") or []
    prof = next((p for p in profiles if isinstance(p, dict) and p.get("id") == profile_id), None)
    if not prof:
        return dict(brand)

    merged = dict(brand)
    for key in ("accountName", "niche", "dialectLabel", "cta", "logoFile", "hashtags"):
        if prof.get(key):
            merged[key] = prof[key]
    merged["colors"] = {**(brand.get("colors") or {}), **(prof.get("colors") or {})}
    return merged


def build_project(
    root_dir: str,
    project_dir: str,
    brand: dict[str, Any],
    settings: dict[str, Any],
    timeline: dict[str, Any],
    video_src_path: str,
) -> dict[str, Any]:
    brand = resolve_brand_profile(brand, settings)
    hf_dir = os.path.join(project_dir, "hf_project")
    comp_dir = os.path.join(hf_dir, "compositions")
    assets_dst = os.path.join(hf_dir, "assets")
    fonts_dst = os.path.join(assets_dst, "fonts")
    media_dst = os.path.join(assets_dst, "media")
    broll_dst = os.path.join(assets_dst, "broll")

    for d in (comp_dir, fonts_dst, media_dst, broll_dst):
        os.makedirs(d, exist_ok=True)

    fonts_src_dir = os.path.join(root_dir, "assets", "fonts")
    if os.path.exists(fonts_src_dir):
        for font_name in os.listdir(fonts_src_dir):
            if font_name.lower().endswith((".ttf", ".otf", ".woff2")):
                shutil.copy2(os.path.join(fonts_src_dir, font_name), os.path.join(fonts_dst, font_name))

    # Use a content-fingerprinted filename so HyperFrames extract-cache NEVER reuses stale uncropped frames
    h = hashlib.sha1()
    st_v = os.stat(video_src_path)
    h.update(f"{st_v.st_size}:{st_v.st_mtime_ns}".encode("utf-8"))
    with open(video_src_path, "rb") as vf:
        h.update(vf.read(65536))
    src_fp = h.hexdigest()[:10]
    source_video_name = f"source_{src_fp}.mp4"
    for old_f in os.listdir(media_dst):
        if old_f.startswith("source") and old_f.endswith(".mp4") and old_f != source_video_name:
            try:
                os.remove(os.path.join(media_dst, old_f))
            except OSError:
                pass
    source_video_dst = os.path.join(media_dst, source_video_name)
    # Preserve mtime if exact same content-hashed video already exists so HyperFrames extract-cache hits 100%!
    if not (os.path.exists(source_video_dst) and os.path.getsize(source_video_dst) == st_v.st_size):
        shutil.copy2(video_src_path, source_video_dst)
    source_video_rel = f"assets/media/{source_video_name}"

    logo_rel = None
    logo_dir = os.path.join(root_dir, "assets", "logo")
    logo_file = brand.get("logoFile", "")
    if not logo_file and os.path.exists(logo_dir):
        candidates = [
            f for f in os.listdir(logo_dir)
            if f.lower().endswith((".png", ".svg", ".webp", ".jpg", ".jpeg"))
        ]
        if candidates:
            logo_file = candidates[0]
    if logo_file and os.path.exists(os.path.join(logo_dir, logo_file)):
        shutil.copy2(os.path.join(logo_dir, logo_file), os.path.join(media_dst, logo_file))
        logo_rel = f"assets/media/{logo_file}"

    broll_src_dir = os.path.join(project_dir, "broll")
    broll_items: list[dict[str, str]] = []
    broll_map: dict[str, dict[str, str]] = {}
    if os.path.exists(broll_src_dir):
        for fname in sorted(os.listdir(broll_src_dir)):
            if fname.lower() == "readme.md":
                continue
            full = os.path.join(broll_src_dir, fname)
            if not os.path.isfile(full):
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
                shutil.copy2(full, os.path.join(broll_dst, fname))
                item = {"type": "image", "src": f"assets/broll/{fname}", "name": fname}
                broll_items.append(item)
                broll_map[fname] = item
            elif ext in (".mp4", ".mov", ".webm"):
                shutil.copy2(full, os.path.join(broll_dst, fname))
                item = {"type": "video", "src": f"assets/broll/{fname}", "name": fname}
                broll_items.append(item)
                broll_map[fname] = item

    duration = max(2.0, float(timeline.get("duration", 5.0)))
    style_mode = settings.get("styleMode", "fast_hook")
    caption_style = settings.get("captionStyle", "karaoke")

    colors = brand.get("colors", {})
    primary = colors.get("primary", "#FFFFFF")
    accent = settings.get("accentOverride") or colors.get("accent", "#FFD60A")
    secondary = colors.get("secondary", "#FF3B30")
    surface_hex = colors.get("surface", "#0C0C10")
    surface_rgba = hex_to_rgba(surface_hex, float(colors.get("surfaceOpacity", 0.78)))

    sz = brand.get("safeZones", {})
    sz_top = max(150, int(sz.get("top", 150)))
    sz_bottom = max(380, int(sz.get("bottom", 380)))
    sz_sides = max(108, int(sz.get("sides", 108)))

    raw_hook_y = settings.get("hookY")
    hook_top_css = f"{max(2.0, min(85.0, float(raw_hook_y))):.2f}%" if raw_hook_y not in (None, "") else f"{sz_top + 104}px"
    raw_cap_y = settings.get("captionsY")
    cap_pos_css = (
        f"top: {max(10.0, min(88.0, float(raw_cap_y))):.2f}%; bottom: auto;"
        if raw_cap_y not in (None, "")
        else f"bottom: {sz_bottom + 24}px;"
    )
    raw_cta_y = settings.get("ctaY")
    cta_pos_css = (
        f"top: {max(10.0, min(85.0, float(raw_cta_y))):.2f}%; bottom: auto;"
        if raw_cta_y not in (None, "")
        else f"bottom: {sz_bottom + 36}px;"
    )
    raw_wm_x = settings.get("watermarkX")
    raw_wm_y = settings.get("watermarkY")
    wm_pos_css = (
        f"left: {max(2.0, min(72.0, float(raw_wm_x))):.2f}%; top: {max(2.0, min(88.0, float(raw_wm_y if raw_wm_y not in (None, '') else 5.0))):.2f}%; right: auto;"
        if raw_wm_x not in (None, "")
        else (
            f"top: {max(2.0, min(88.0, float(raw_wm_y))):.2f}%; right: {sz_sides}px;"
            if raw_wm_y not in (None, "")
            else f"top: {sz_top + 4}px; right: {sz_sides}px;"
        )
    )
    show_watermark = settings.get("showWatermark", True) is not False

    hook_title = (settings.get("hookTitle") if settings.get("hookTitle") is not None else (timeline.get("auto_hook") or "")).strip()
    cta_text = (settings.get("ctaText") or brand.get("cta") or "تابعني ومش هتندم").strip()
    account_name = (brand.get("accountName") or "").strip()

    captions = timeline.get("captions", [])
    cut_points = timeline.get("cut_points", [])

    sfx_db = float(settings.get("sfxDb", -5) or -5)
    sfx_cues = []
    teaser_dur = max(0.0, float(timeline.get("teaser_duration") or 0.0))
    teaser_badge = (settings.get("teaserBadge") or timeline.get("teaser_badge") or "شاهد للنهاية 🔥").strip()
    show_hook_card = settings.get("showHookCard", True) is not False

    if teaser_dur > 0.5:
        hook_dur = 0.0
        sfx_cues.append({"file": os.path.join(root_dir, "assets", "sfx", "whoosh.wav"), "time": 0.04, "volume_db": sfx_db})
        sfx_cues.append({
            "file": os.path.join(root_dir, "assets", "sfx", "whoosh.wav"),
            "time": max(0.2, round(teaser_dur - 0.08, 2)),
            "volume_db": sfx_db + 1.0,
        })
    elif hook_title and show_hook_card:
        hook_dur = min(2.8, max(1.6, duration * 0.34))
        try:
            _hd = settings.get("hookDuration")
            if _hd not in (None, ""):
                hook_dur = max(0.8, min(8.0, float(_hd), duration * 0.6))
        except (TypeError, ValueError):
            pass
        sfx_cues.append({"file": os.path.join(root_dir, "assets", "sfx", "whoosh.wav"), "time": 0.04, "volume_db": sfx_db})
    else:
        hook_dur = 0.0

    salawat_outro = bool(settings.get("salawatOutro", False))
    if salawat_outro and duration >= 4.2:
        cta_dur = min(3.4, max(2.2, duration * 0.28))
    elif cta_text and duration >= 4.2:
        cta_dur = min(2.8, max(1.8, duration * 0.25))
    else:
        cta_dur = 0.0
    cta_start = round(max(0.0, duration - cta_dur), 3)
    if cta_dur > 0:
        sfx_cues.append({
            "file": os.path.join(root_dir, "assets", "sfx", "riser.wav"),
            "time": max(0.0, round(cta_start - 0.65, 2)),
            "volume_db": sfx_db,
        })
        sfx_cues.append({
            "file": os.path.join(root_dir, "assets", "sfx", "chime.wav"),
            "time": round(cta_start, 2),
            "volume_db": sfx_db - 1.0,
        })

    # --- 1. Opening Whip-Zoom + Light-Leak Flash + Cut-Zoom Alternation ---
    zoom_scale = 1.08 if style_mode == "fast_hook" else (1.05 if style_mode == "educational" else 1.035)
    zoom_tweens_list = [
        # Opening Whip-Zoom punch-in
        '    tl.fromTo("#video-stage", { scale: 1.15, y: -16 }, { scale: 1.0, y: 0, duration: 0.42, ease: "expo.out" }, 0);',
        '    tl.fromTo("#light-flash", { opacity: 0.52 }, { opacity: 0, duration: 0.38, ease: "power2.out" }, 0);',
    ]

    # Cut-Zoom Alternation & kinetic shot-cut pulses on silence-cut transitions (non-overlapping!)
    zoomed_in = False
    last_cut_sfx = -1.0
    last_stage_t = 0.45
    for cp in (cut_points or []):
        cp_t = round(float(cp), 3)
        if cp_t <= last_stage_t + 0.35 or cp_t >= duration - 0.5:
            continue
        zoomed_in = not zoomed_in
        target_s = zoom_scale if zoomed_in else 1.0
        zoom_tweens_list.append(
            f'    tl.to("#video-stage", {{ scale: {target_s}, x: {8 if zoomed_in else 0}, duration: 0.28, ease: "power2.out", overwrite: "auto" }}, {cp_t});'
        )
        last_stage_t = cp_t + 0.28
        if cp_t - last_cut_sfx >= 1.5:
            sfx_cues.append({
                "file": os.path.join(root_dir, "assets", "sfx", "whoosh.wav"),
                "time": max(0.0, round(cp_t - 0.06, 2)),
                "volume_db": sfx_db - 1.5,
            })
            last_cut_sfx = cp_t

    # Regular camera motion beats if few cut_points
    if len(cut_points) < 2 and duration >= 3.5:
        step = 3.2 if style_mode == "fast_hook" else 4.5
        t = 1.4
        idx_z = 0
        while t < duration - 1.2:
            pan_x = 12.0 if idx_z % 2 == 0 else -12.0
            hold_d = round(min(1.6, (duration - t) * 0.45), 2)
            zoom_tweens_list.append(
                f'    tl.to("#video-stage", {{ scale: {zoom_scale}, x: {pan_x}, y: -10, duration: 0.34, ease: "power2.out", overwrite: "auto" }}, {round(t, 2)});\n'
                f'    tl.to("#video-stage", {{ scale: 1.0, x: 0, y: 0, duration: 0.42, ease: "power2.inOut", overwrite: "auto" }}, {round(t + hold_d, 2)});'
            )
            t += step
            idx_z += 1

    # Explicit per-caption strong zoom cues
    for i, ch in enumerate(captions):
        if ch.get("zoom"):
            zs = round(float(ch.get("start", 0.0)), 3)
            ze = round(min(duration - 0.1, float(ch.get("end", zs + 1.2))), 3)
            zoom_tweens_list.append(
                f'    tl.to("#video-stage", {{ scale: {round(zoom_scale + 0.04, 2)}, duration: 0.25, ease: "power3.out", overwrite: "auto" }}, {zs});\n'
                f'    tl.to("#video-stage", {{ scale: 1.0, duration: 0.32, ease: "power2.inOut", overwrite: "auto" }}, {ze});'
            )

    # --- 2. Lightweight Deterministic 7-Bar Audio Waveform Visualizer (1 tween instead of 2,700!) ---
    wave_tweens = [
        '    const _wbars = [0, 1, 2, 3, 4, 5, 6].map((i) => document.getElementById("wb-" + i));',
        '    const _waveDriver = { t: 0 };',
        f'    tl.to(_waveDriver, {{ t: {round(duration, 3)}, duration: {round(duration, 3)}, ease: "none", onUpdate: () => {{ const tw = _waveDriver.t; for (let i = 0; i < 7; i++) {{ if (_wbars[i]) _wbars[i].style.transform = "scaleY(" + (0.28 + 0.72 * Math.abs(Math.sin(tw * 5.2 + i * 0.95))).toFixed(3) + ")"; }} }} }}, 0);',
    ]

    # --- 3. Smart Kinetic Callouts (disabled by default to avoid noisy/misheard popups) ---
    callouts = []
    enable_callouts = bool(settings.get("enableCallouts", False))
    last_callout_t = max(2.0, hook_dur + 0.15)
    for idx, ch in enumerate(captions if enable_callouts else []):
        c_start = float(ch.get("start", 0.0))
        c_end = float(ch.get("end", c_start + 1.0))
        if c_start < last_callout_t or c_start > duration - cta_dur - 1.0:
            continue
        txt = (ch.get("text") or "").strip()
        if not txt:
            continue
        num_match = NUMBER_RE.search(txt)
        tokens = [w for w in txt.split() if w.strip(".,،!?؟") not in STOP_WORDS_AR]
        if num_match:
            callouts.append({
                "id": f"callout-{len(callouts)}",
                "start": round(c_start, 3),
                "duration": round(min(2.2, max(1.2, c_end - c_start + 0.5)), 3),
                "badge": num_match.group(0),
                "label": txt[:30],
            })
            sfx_cues.append({"file": os.path.join(root_dir, "assets", "sfx", "pop.wav"), "time": round(c_start, 2), "volume_db": sfx_db - 1.5})
            last_callout_t = c_start + 4.4
        elif tokens:
            callouts.append({
                "id": f"callout-{len(callouts)}",
                "start": round(c_start, 3),
                "duration": round(min(2.0, max(1.1, c_end - c_start + 0.4)), 3),
                "badge": "✦",
                "label": txt[:30],
            })
            sfx_cues.append({"file": os.path.join(root_dir, "assets", "sfx", "pop.wav"), "time": round(c_start, 2), "volume_db": sfx_db - 2.0})
            last_callout_t = c_start + 4.8

    # --- 4. B-Roll Scheduling (Explicit caption cues first, then auto-distribute remaining) ---
    broll_html_list = []
    broll_tweens = []
    used_broll_names: set[str] = set()

    def add_broll_clip(bid: str, item: dict[str, str], b_start: float, b_dur: float) -> None:
        inner = (
            f'<img src="{item["src"]}" alt="" class="broll-media" />'
            if item["type"] == "image"
            else f'<video src="{item["src"]}" muted class="broll-media" data-start="0" data-duration="{b_dur}"></video>'
        )
        broll_html_list.append(
            f'      <div id="{bid}-clip" class="clip broll-clip" data-start="{b_start}" data-duration="{b_dur}" data-track-index="4">\n'
            f'        <div id="{bid}-card" class="broll-card">{inner}</div>\n'
            f'      </div>'
        )
        broll_tweens.append(
            f'    tl.fromTo("#{bid}-card", {{ y: -26, scale: 0.92, opacity: 0 }}, {{ y: 0, scale: 1, opacity: 1, duration: 0.32, ease: "back.out(1.4)" }}, {b_start});\n'
            f'    tl.to("#{bid}-card", {{ y: -16, opacity: 0, duration: 0.22, ease: "power2.in" }}, {round(b_start + b_dur - 0.25, 3)});'
        )
        sfx_cues.append({"file": os.path.join(root_dir, "assets", "sfx", "chime.wav"), "time": round(b_start, 2), "volume_db": sfx_db - 1.0})

    broll_idx = 0
    for ch in captions:
        bname = (ch.get("broll") or "").strip()
        if bname and bname in broll_map:
            bs = round(float(ch.get("start", 0.0)), 3)
            bd = round(min(3.2, max(1.4, float(ch.get("end", bs + 2.0)) - bs + 0.8)), 3)
            if bs + bd > duration - 0.2:
                bd = max(0.8, round(duration - 0.2 - bs, 3))
            add_broll_clip(f"broll-{broll_idx}", broll_map[bname], bs, bd)
            used_broll_names.add(bname)
            broll_idx += 1

    remaining_broll = [it for it in broll_items if it["name"] not in used_broll_names]
    if remaining_broll and duration > 5.0:
        win_start = max(2.4, hook_dur + 0.3)
        win_end = max(win_start + 2.0, cta_start - 0.5)
        span = win_end - win_start
        slot = span / len(remaining_broll)
        for item in remaining_broll:
            b_start = round(win_start + broll_idx * slot, 3)
            b_dur = round(min(3.2, max(1.7, slot * 0.72)), 3)
            if b_start + b_dur > duration - 0.3:
                b_dur = max(1.0, round(duration - 0.3 - b_start, 3))
            add_broll_clip(f"broll-{broll_idx}", item, b_start, b_dur)
            broll_idx += 1

    # --- 5. Captions (Karaoke Word-by-Word OR Highlighted Chunk) + Smart Emoji Pop-ups ---
    show_captions = settings.get("showCaptions", True) is not False
    caption_divs = []
    caption_tweens = []
    for i, ch in enumerate(captions if show_captions else []):
        c_start = round(max(0.0, float(ch.get("start", 0.0))), 3)
        next_start = float(captions[i + 1]["start"]) if i + 1 < len(captions) else duration - 0.05
        raw_end = min(duration - 0.05, float(ch.get("end", c_start + 1.0)), next_start - 0.02)
        c_dur = round(max(0.28, raw_end - c_start), 3)
        if c_start >= duration - 0.15:
            continue
        cid = f"cap-{i}"
        raw_text = (ch.get("text") or "").strip()
        if not raw_text:
            continue
        hl_word = (ch.get("highlight") or "").strip()
        emoji = detect_keyword_emoji(raw_text)
        emoji_html = f'<div id="{cid}-emoji" class="emoji-pop">{emoji}</div>' if emoji else ""

        if caption_style == "karaoke":
            words_arr = ch.get("words") or []
            tokens = raw_text.split()
            word_spans = []
            # Build per-word timing (use Whisper word timestamps if count matches, else distribute evenly)
            use_exact = len(words_arr) == len(tokens) and len(words_arr) > 0
            step_w = c_dur / max(1, len(tokens))
            for j, tok in enumerate(tokens):
                wid = f"kw-{i}-{j}"
                esc = html.escape(tok)
                is_lat = bool(LATIN_RE.fullmatch(tok.strip(".,،!?؟")))
                dir_attr = ' dir="ltr"' if is_lat else ""
                word_spans.append(f'<span id="{wid}" class="kw"{dir_attr}>{esc}</span>')
                wt = float(words_arr[j]["start"]) if use_exact else (c_start + j * step_w)
                wt = round(max(c_start, min(c_start + c_dur - 0.08, wt)), 3)
                caption_tweens.append(
                    f'    tl.fromTo("#{wid}", {{ color: "{primary}", scale: 1 }}, {{ color: "{accent}", scale: 1.06, duration: 0.09, ease: "back.out(2.2)" }}, {wt});'
                )
            inner_cap = " ".join(word_spans)
        else:
            inner_cap = format_rtl_html(raw_text, hl_word)

        bilingual_on = settings.get("bilingualCaptions", True) is not False
        en_sub = (ch.get("en_text") or "").strip() if bilingual_on else ""
        # Never show a duplicate subtitle pill if translation echoed the exact same text back
        if en_sub and re.sub(r"[\s.,،!?؟]+", "", en_sub).lower() == re.sub(r"[\s.,،!?؟]+", "", raw_text).lower():
            en_sub = ""
        en_html = f'\n        <div id="{cid}-en" class="cap-en-sub" dir="ltr">{html.escape(en_sub)}</div>' if en_sub else ""

        rot_start = 1.4 if i % 2 == 0 else -1.4
        caption_divs.append(
            f'      <div id="{cid}-clip" class="clip cap-clip" data-start="{c_start}" data-duration="{c_dur}" data-track-index="2">\n'
            f'        {emoji_html}\n'
            f'        <div id="{cid}-box" class="cap-box cap-{caption_style}">{inner_cap}</div>{en_html}\n'
            f'      </div>'
        )
        caption_tweens.append(
            f'    tl.fromTo("#{cid}-box", {{ y: 22, scale: 0.88, rotation: {rot_start}, opacity: 0 }}, {{ y: 0, scale: 1, rotation: 0, opacity: 1, duration: 0.16, ease: "back.out(1.8)" }}, {c_start});'
        )
        if en_sub:
            caption_tweens.append(
                f'    tl.fromTo("#{cid}-en", {{ y: 12, opacity: 0 }}, {{ y: 0, opacity: 1, duration: 0.18, ease: "power2.out" }}, {c_start});'
            )
        if emoji:
            caption_tweens.append(
                f'    tl.fromTo("#{cid}-emoji", {{ y: 24, scale: 0.2, opacity: 0 }}, {{ y: 0, scale: 1.08, opacity: 1, duration: 0.24, ease: "back.out(2.4)" }}, {c_start});'
            )

    # --- 6. Callouts HTML & Tweens ---
    callout_html_list = []
    callout_tweens = []
    for co in callouts:
        coid = co["id"]
        c_start = co["start"]
        c_dur = co["duration"]
        callout_html_list.append(
            f'      <div id="{coid}-clip" class="clip callout-clip" data-start="{c_start}" data-duration="{c_dur}" data-track-index="3">\n'
            f'        <div id="{coid}-card" class="callout-card">\n'
            f'          <span class="callout-num ltr">{html.escape(co["badge"])}</span>\n'
            f'          <span class="callout-lbl">{html.escape(co["label"])}</span>\n'
            f'        </div>\n'
            f'      </div>'
        )
        callout_tweens.append(
            f'    tl.fromTo("#{coid}-card", {{ y: -24, scale: 0.88, opacity: 0 }}, {{ y: 0, scale: 1, opacity: 1, duration: 0.28, ease: "back.out(1.6)" }}, {c_start});\n'
            f'    tl.to("#{coid}-card", {{ opacity: 0, y: -14, duration: 0.2, ease: "power2.in" }}, {round(c_start + c_dur - 0.22, 3)});'
        )

    # --- 7. Hook + 3s Teaser Card + Custom Title Patches / Blur Masks + Watermark + CTA ---
    hook_html = ""
    hook_tweens = ""
    if teaser_dur > 0.5:
        teaser_end = round(max(0.4, teaser_dur - 0.08), 3)
        if show_hook_card and hook_title:
            hook_html = (
                f'      <div id="teaser-clip" class="clip hook-clip" data-start="0" data-duration="{teaser_end}" data-track-index="1">\n'
                f'        <div id="teaser-card" class="hook-card teaser-card">\n'
                f'          <div class="teaser-badge-row">\n'
                f'            <span class="teaser-dot"></span>\n'
                f'            <span>{html.escape(teaser_badge)}</span>\n'
                f'          </div>\n'
                f'          <h1 class="hook-title teaser-sub">{format_rtl_html(hook_title)}</h1>\n'
                f'          <div class="teaser-timer-track"><div id="teaser-timer-fill" class="teaser-timer-fill"></div></div>\n'
                f'        </div>\n'
                f'      </div>'
            )
        else:
            hook_html = (
                f'      <div id="teaser-clip" class="clip teaser-hud-clip" data-start="0" data-duration="{teaser_end}" data-track-index="1">\n'
                f'        <div id="teaser-card" class="teaser-pill-compact">\n'
                f'          <span class="teaser-dot"></span>\n'
                f'          <span>{html.escape(teaser_badge)}</span>\n'
                f'          <div id="teaser-timer-fill" class="teaser-mini-bar"></div>\n'
                f'        </div>\n'
                f'      </div>'
            )
        hook_tweens = (
            f'    tl.fromTo("#teaser-card", {{ y: -14, scale: 0.94, opacity: 0.92 }}, {{ y: 0, scale: 1, opacity: 1, duration: 0.28, ease: "back.out(1.6)" }}, 0);\n'
            f'    tl.fromTo("#teaser-timer-fill", {{ scaleX: 1 }}, {{ scaleX: 0, duration: {teaser_end}, ease: "none" }}, 0);\n'
            f'    tl.fromTo("#light-flash", {{ opacity: 0.58 }}, {{ opacity: 0, duration: 0.36, ease: "power2.out", immediateRender: false }}, {round(max(0.0, teaser_dur - 0.1), 3)});'
        )
    elif hook_title and hook_dur > 0:
        hook_html = (
            f'      <div id="hook-clip" class="clip hook-clip" data-start="0" data-duration="{round(hook_dur, 3)}" data-track-index="1">\n'
            f'        <div id="hook-card" class="hook-card">\n'
            f'          <div class="hook-pill">{html.escape(account_name or "PRO REEL")}</div>\n'
            f'          <h1 class="hook-title">{format_rtl_html(hook_title)}</h1>\n'
            f'          <div id="hook-line" class="hook-underline"></div>\n'
            f'        </div>\n'
            f'      </div>'
        )
        hook_tweens = (
            f'    tl.fromTo("#hook-card", {{ y: -18, scale: 0.94, opacity: 0.92 }}, {{ y: 0, scale: 1, opacity: 1, duration: 0.34, ease: "back.out(1.5)" }}, 0);\n'
            f'    tl.fromTo("#hook-line", {{ scaleX: 0 }}, {{ scaleX: 1, duration: 0.45, ease: "power3.out" }}, 0.12);\n'
            f'    tl.to("#hook-card", {{ y: -28, opacity: 0, duration: 0.24, ease: "power2.in" }}, {round(hook_dur - 0.26, 3)});'
        )

    overlay_html_list: list[str] = []
    overlay_tweens: list[str] = []
    for ov_i, ov in enumerate(settings.get("overlays") or []):
        if not isinstance(ov, dict):
            continue
        mode = (ov.get("mode") or "replace").strip()
        if mode == "delogo":
            continue
        ox = max(0.0, min(95.0, float(ov.get("x") or 8.0)))
        oy = max(0.0, min(95.0, float(ov.get("y") or 12.0)))
        ow = max(6.0, min(100.0 - ox, float(ov.get("w") or 84.0)))
        oh = max(4.0, min(100.0 - oy, float(ov.get("h") or 11.0)))
        ov_start = max(0.0, float(ov.get("start") or 0.0))
        ov_end = float(ov.get("end") or 0.0)
        if ov_end <= ov_start:
            ov_end = duration
        ov_end = min(duration, ov_end)
        ov_dur = round(max(0.2, ov_end - ov_start), 3)
        ovid = f"ov-{ov_i}"

        if mode == "blur":
            overlay_html_list.append(
                f'      <div id="{ovid}" class="clip ov-blur" data-start="{round(ov_start, 3)}" '
                f'data-duration="{ov_dur}" data-track-index="4" '
                f'style="left:{ox:.2f}%; top:{oy:.2f}%; width:{ow:.2f}%; height:{oh:.2f}%;"></div>'
            )
            if ov_start > 0.05:
                overlay_tweens.append(
                    f'    tl.fromTo("#{ovid}", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.18, ease: "power2.out" }}, {round(ov_start, 3)});'
                )
        elif mode == "replace":
            card_style = ov.get("cardStyle") or "solid_dark"
            if card_style not in ("solid_dark", "glass_gold", "cinema_bar", "accent_pill"):
                card_style = "solid_dark"
            font_sz = max(20, min(130, int(float(ov.get("fontSize") or 46))))
            txt_col = (ov.get("textColor") or "#FFFFFF").strip()
            # Ensure high contrast on dark card styles (prevent black-on-black text!)
            if card_style in ("solid_dark", "glass_gold", "cinema_bar") and txt_col.startswith("#") and len(txt_col) == 7:
                try:
                    rr, gg, bb = int(txt_col[1:3], 16), int(txt_col[3:5], 16), int(txt_col[5:7], 16)
                    if (0.299 * rr + 0.587 * gg + 0.114 * bb) < 60:
                        txt_col = "#FFFFFF"
                except ValueError:
                    txt_col = "#FFFFFF"
            ov_font_key = (ov.get("fontFamily") or settings.get("arabicFont") or "cairo").strip().lower()
            # IMPORTANT: Use single quotes inside HTML style="..." attribute so double quotes never truncate style!
            ov_font_css = "'" + font_css_name(ov_font_key) + "'"
            txt = (ov.get("text") or "").strip().replace("_", " ")
            if txt:
                # Render clean uniform text color (no random power-word yellow highlight on custom boxes)
                text_markup = "<br/>".join(html.escape(line) for line in txt.splitlines())
            else:
                text_markup = "&nbsp;"
            text_inline_color = "#080a0f" if card_style == "accent_pill" else txt_col
            overlay_html_list.append(
                f'      <div id="{ovid}" class="clip ov-patch ov-style-{card_style}" data-start="{round(ov_start, 3)}" '
                f'data-duration="{ov_dur}" data-track-index="4" '
                f'style="left:{ox:.2f}%; top:{oy:.2f}%; width:{ow:.2f}%; height:{oh:.2f}%; '
                f'font-size:{font_sz}px; font-family:{ov_font_css}, sans-serif; color:{html.escape(text_inline_color)};">'
                f'<div class="ov-patch-text" style="color:{html.escape(text_inline_color)};">{text_markup}</div></div>'
            )
            if ov_start > 0.05:
                overlay_tweens.append(
                    f'    tl.fromTo("#{ovid}", {{ opacity: 0, scale: 0.96 }}, {{ opacity: 1, scale: 1, duration: 0.18, ease: "power2.out" }}, {round(ov_start, 3)});'
                )
        elif mode in ("image", "video"):
            mfile = os.path.basename(str(ov.get("mediaFile") or ""))
            src_media = os.path.join(project_dir, "broll", mfile) if mfile else ""
            if mfile and os.path.exists(src_media):
                dest_media = os.path.join(media_dst, mfile)
                if not os.path.exists(dest_media):
                    shutil.copy2(src_media, dest_media)
                media_rel = f"assets/media/{mfile}"
                if mode == "image":
                    inner_tag = f'<img src="{html.escape(media_rel)}" class="ov-media-el" alt="" />'
                else:
                    inner_tag = f'<video src="{html.escape(media_rel)}" class="ov-media-el" muted playsinline preload="auto"></video>'
                overlay_html_list.append(
                    f'      <div id="{ovid}" class="clip ov-media" data-start="{round(ov_start, 3)}" '
                    f'data-duration="{ov_dur}" data-track-index="4" '
                    f'style="left:{ox:.2f}%; top:{oy:.2f}%; width:{ow:.2f}%; height:{oh:.2f}%;">{inner_tag}</div>'
                )
                if ov_start > 0.05:
                    overlay_tweens.append(
                        f'    tl.fromTo("#{ovid}", {{ opacity: 0, scale: 0.94 }}, {{ opacity: 1, scale: 1, duration: 0.2, ease: "power2.out" }}, {round(ov_start, 3)});'
                    )

    wm_logo = f'<img src="{logo_rel}" class="wm-logo" alt="{html.escape(account_name)}" />' if logo_rel else '<span class="wm-dot"></span>'
    watermark_html = (
        f'    <div class="watermark-pill">\n'
        f'      {wm_logo}\n'
        f'      <span class="wm-name">{html.escape(account_name or "غناوي هلنا")}</span>\n'
        f'    </div>'
    ) if show_watermark else ""

    cta_html = ""
    cta_tweens = ""
    if cta_dur > 0 and salawat_outro:
        salawat_handle = f'<div class="salawat-handle">{html.escape(account_name)}</div>' if account_name else ""
        star_svg = (
            '<svg class="salawat-ornament" viewBox="0 0 180 20" fill="none" xmlns="http://www.w3.org/2000/svg">'
            f'<line x1="6" y1="10" x2="72" y2="10" stroke="{accent}" stroke-opacity="0.65" stroke-width="2" stroke-linecap="round"/>'
            f'<path d="M90 2 L92.6 7.4 L98 10 L92.6 12.6 L90 18 L87.4 12.6 L82 10 L87.4 7.4 Z" fill="{accent}"/>'
            f'<line x1="108" y1="10" x2="174" y2="10" stroke="{accent}" stroke-opacity="0.65" stroke-width="2" stroke-linecap="round"/>'
            '</svg>'
        )
        cta_html = (
            f'      <div id="cta-clip" class="clip cta-clip" data-start="{cta_start}" data-duration="{round(cta_dur - 0.04, 3)}" data-track-index="5">\n'
            f'        <div id="cta-card" class="salawat-card">\n'
            f'          <div id="cta-shimmer" class="card-shimmer"></div>\n'
            f'          <div class="salawat-badge">🌙 تذكرة جميلة ✨</div>\n'
            f'          <div class="salawat-lead">إذا وصلت لنهاية الفيديو</div>\n'
            f'          <div class="salawat-main">صلِّ على النبي ﷺ</div>\n'
            f'          {star_svg}\n'
            f'          <div class="salawat-sub">اللهم صلِّ وسلِّم وبارك على نبينا محمد 🤍</div>\n'
            f'          {salawat_handle}\n'
            f'        </div>\n'
            f'      </div>'
        )
        cta_tweens = (
            f'    tl.fromTo("#light-flash", {{ opacity: 0.42 }}, {{ opacity: 0, duration: 0.48, ease: "power2.out", immediateRender: false }}, {cta_start});\n'
            f'    tl.fromTo("#cta-card", {{ y: 48, scale: 0.88, opacity: 0 }}, {{ y: 0, scale: 1, opacity: 1, duration: 0.42, ease: "back.out(1.45)" }}, {cta_start});\n'
            f'    tl.fromTo("#cta-shimmer", {{ xPercent: -140 }}, {{ xPercent: 160, duration: 1.05, ease: "power2.inOut" }}, {round(cta_start + 0.32, 3)});\n'
            f'    tl.to("#cta-card", {{ scale: 1.03, duration: 0.65, ease: "sine.inOut" }}, {round(cta_start + 1.0, 3)});\n'
            f'    tl.to("#cta-card", {{ scale: 1.0, duration: 0.65, ease: "sine.inOut" }}, {round(cta_start + 1.65, 3)});'
        )
    elif cta_text and cta_dur > 0:
        logo_tag = f'<img src="{logo_rel}" class="cta-logo" alt="" />' if logo_rel else ""
        cta_html = (
            f'      <div id="cta-clip" class="clip cta-clip" data-start="{cta_start}" data-duration="{round(cta_dur - 0.04, 3)}" data-track-index="5">\n'
            f'        <div id="cta-card" class="cta-card">\n'
            f'          <div id="cta-shimmer" class="card-shimmer"></div>\n'
            f'          {logo_tag}\n'
            f'          <div class="cta-text">{html.escape(cta_text)}</div>\n'
            f'          <div class="cta-handle">{html.escape(account_name)}</div>\n'
            f'        </div>\n'
            f'      </div>'
        )
        cta_tweens = (
            f'    tl.fromTo("#light-flash", {{ opacity: 0.36 }}, {{ opacity: 0, duration: 0.38, ease: "power2.out", immediateRender: false }}, {cta_start});\n'
            f'    tl.fromTo("#cta-card", {{ y: 40, scale: 0.9, opacity: 0 }}, {{ y: 0, scale: 1, opacity: 1, duration: 0.36, ease: "back.out(1.5)" }}, {cta_start});\n'
            f'    tl.fromTo("#cta-shimmer", {{ xPercent: -140 }}, {{ xPercent: 160, duration: 0.95, ease: "power2.inOut" }}, {round(cta_start + 0.28, 3)});\n'
            f'    tl.to("#cta-card", {{ scale: 1.03, duration: 0.45, ease: "sine.inOut" }}, {round(cta_start + 0.9, 3)});'
        )

    prog_track_w = max(200, 1080 - (2 * sz_sides) - 6)
    prog_dur = round(max(0.2, duration - 0.05), 3)
    prog_tween = (
        f'    tl.fromTo("#progress-fill", {{ scaleX: 0 }}, {{ scaleX: 1, duration: {prog_dur}, ease: "none" }}, 0);\n'
        f'    tl.fromTo("#progress-tip", {{ x: 0, opacity: 0.9 }}, {{ x: -{prog_track_w}, opacity: 1, duration: {prog_dur}, ease: "none" }}, 0);'
    )

    wave_bars_html = "\n".join(
        f'      <span id="wb-{b}" class="wbar"></span>' for b in range(7)
    )

    root_font_key = (settings.get("arabicFont") or brand.get("defaults", {}).get("arabicFont") or "cairo").strip().lower()
    root_font_css = '"' + font_css_name(root_font_key) + '"'
    hook_font_css = '"' + font_css_name(settings.get("hookFont") or root_font_key) + '"'
    cap_font_css = '"' + font_css_name(settings.get("captionFont") or root_font_key) + '"'
    _cs = settings.get("captionSize"); _cc = settings.get("captionColor")
    _hs = settings.get("hookSize"); _hc = settings.get("hookColor")
    custom_css = f'''
    .cap-box {{ font-family: {cap_font_css}, "CairoPro", sans-serif; }}
    .hook-title, .hook-pill {{ font-family: {hook_font_css}, "CairoPro", sans-serif; }}
'''
    if _cs not in (None, ""):
        custom_css += f"    .cap-box {{ font-size: {max(24, min(96, int(float(_cs))))}px; }}\n"
    if _cc:
        custom_css += f"    .cap-box {{ color: {html.escape(str(_cc))}; }}\n"
    if _hs not in (None, ""):
        custom_css += f"    .hook-title {{ font-size: {max(28, min(120, int(float(_hs))))}px; }}\n"
    if _hc:
        custom_css += f"    .hook-title {{ color: {html.escape(str(_hc))}; }}\n"
    if settings.get("showHookPill", True) is False:
        custom_css += "    .hook-pill { display: none; }\n"
    _hbg = settings.get("hookBg")
    if _hbg:
        custom_css += f"    .hook-card {{ background: {html.escape(str(_hbg))}; }}\n"
    _hb = settings.get("hookBorder")
    if _hb:
        custom_css += f"    .hook-card {{ border-color: {html.escape(str(_hb))}; }}\n"
    font_faces = font_faces_css()

    reel_html = f"""<template>
  <style>
{font_faces}
    @font-face {{
      font-family: "MontserratPro";
      src: url("assets/fonts/Montserrat-Variable.ttf") format("truetype");
      font-weight: 300 900;
      font-style: normal;
      font-display: swap;
    }}

    #root {{
      position: absolute;
      inset: 0;
      overflow: hidden;
      background: #04060a;
      font-family: {root_font_css}, "CairoPro", "MontserratPro", sans-serif;
      direction: rtl;
    }}

    .video-stage {{
      position: absolute;
      inset: 0;
      transform-origin: center 42%;
    }}

    .main-video {{
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
    }}

    .cinema-vignette {{
      position: absolute;
      inset: 0;
      pointer-events: none;
      background:
        linear-gradient(180deg, rgba(4,6,10,0.48) 0%, rgba(4,6,10,0.0) 24%, rgba(4,6,10,0.0) 62%, rgba(4,6,10,0.74) 100%);
    }}

    .light-flash {{
      position: absolute;
      inset: 0;
      pointer-events: none;
      background: radial-gradient(circle at 50% 38%, {hex_to_rgba(accent, 0.55)} 0%, rgba(255,255,255,0.22) 35%, transparent 72%);
      opacity: 0;
      z-index: 22;
    }}

    .progress-bar {{
      position: absolute;
      top: {sz_top - 26}px;
      left: {sz_sides}px;
      right: {sz_sides}px;
      height: 18px;
      padding: 3px;
      border-radius: 999px;
      background: rgba(6, 10, 18, 0.76);
      border: 2px solid rgba(255, 255, 255, 0.28);
      box-shadow: 0 8px 26px rgba(0, 0, 0, 0.68), inset 0 2px 6px rgba(0, 0, 0, 0.72);
      overflow: visible;
      z-index: 25;
    }}

    .progress-track {{
      width: 100%;
      height: 100%;
      border-radius: 999px;
      overflow: hidden;
      background: rgba(255, 255, 255, 0.10);
    }}

    .progress-fill {{
      width: 100%;
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, #FFF3B0 0%, {accent} 42%, {secondary} 100%);
      box-shadow: 0 0 20px {hex_to_rgba(accent, 0.90)}, inset 0 2px 3px rgba(255, 255, 255, 0.45);
      transform-origin: right center;
    }}

    .progress-tip {{
      position: absolute;
      top: 50%;
      right: -4px;
      width: 24px;
      height: 24px;
      margin-top: -12px;
      border-radius: 50%;
      background: radial-gradient(circle, #FFFFFF 0%, #FFF3B0 42%, {accent} 74%, transparent 100%);
      box-shadow: 0 0 22px {hex_to_rgba(accent, 0.95)}, 0 0 10px #FFFFFF;
      pointer-events: none;
    }}

    /* Top HUD: Brand Watermark + Audio Waveform */
    .watermark-pill {{
      position: absolute;
      {wm_pos_css}
      z-index: 45;
      display: inline-flex;
      align-items: center;
      gap: 12px;
      padding: 6px 20px 6px 8px;
      border-radius: 999px;
      background: rgba(8, 12, 22, 0.90);
      border: 1.5px solid rgba(255, 214, 10, 0.42);
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.7), 0 0 18px rgba(255, 214, 10, 0.2);
      color: #FFFFFF;
      pointer-events: none;
    }}

    .wm-logo {{
      width: 52px;
      height: 52px;
      border-radius: 50%;
      object-fit: cover;
      border: 2px solid {accent};
      box-shadow: 0 0 14px rgba(255, 214, 10, 0.5);
      flex-shrink: 0;
    }}

    .wm-name {{
      font-size: 26px;
      font-weight: 900;
      letter-spacing: 0.5px;
      color: #FFFFFF;
      text-shadow: 0 2px 8px rgba(0, 0, 0, 0.9);
      white-space: nowrap;
    }}

    .wm-dot {{
      width: 16px;
      height: 16px;
      border-radius: 50%;
      background: {accent};
      box-shadow: 0 0 12px {accent};
    }}

    .wave-pill {{
      position: absolute;
      top: {sz_top + 4}px;
      left: {sz_sides}px;
      z-index: 45;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      height: 66px;
      padding: 14px 20px;
      border-radius: 999px;
      background: rgba(8, 12, 22, 0.90);
      border: 1.5px solid rgba(255, 255, 255, 0.18);
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
    }}

    .wbar {{
      width: 6px;
      height: 30px;
      border-radius: 999px;
      background: linear-gradient(180deg, #FFF3B0 0%, {accent} 58%, {secondary} 100%);
      box-shadow: 0 0 10px {hex_to_rgba(accent, 0.55)};
      transform-origin: center center;
    }}

    /* Hook Card (0-2.8s) */
    .hook-clip {{
      position: absolute;
      top: {hook_top_css};
      left: {sz_sides}px;
      right: {sz_sides}px;
      z-index: 32;
      display: flex;
      justify-content: center;
    }}

    .hook-card {{
      width: 100%;
      padding: 26px 30px;
      border-radius: 26px;
      background: {surface_rgba};
      border: 2.5px solid {accent};
      box-shadow: 0 22px 54px rgba(0, 0, 0, 0.58);
      text-align: center;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 12px;
    }}

    .hook-pill {{
      padding: 6px 20px;
      border-radius: 999px;
      background: {accent};
      color: #080a0f;
      font-size: 23px;
      font-weight: 900;
    }}

    .hook-title {{
      color: {primary};
      font-size: 54px;
      font-weight: 900;
      line-height: 1.25;
    }}

    .hook-underline {{
      width: 220px;
      height: 6px;
      border-radius: 999px;
      background: linear-gradient(90deg, {accent}, {secondary});
      transform-origin: center center;
    }}

    /* 3s Viral Teaser Banner */
    .teaser-card {{
      padding: 20px 28px;
      border-color: {secondary};
      background: rgba(10, 12, 20, 0.88);
    }}

    .teaser-badge-row {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 7px 22px;
      border-radius: 999px;
      background: linear-gradient(90deg, {secondary}, {accent});
      color: #080a0f;
      font-size: 26px;
      font-weight: 900;
    }}

    .teaser-dot {{
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: #080a0f;
    }}

    .hook-title.teaser-sub {{
      font-size: 46px;
    }}

    .teaser-timer-track {{
      width: 100%;
      height: 7px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.16);
      overflow: hidden;
      margin-top: 4px;
    }}

    .teaser-timer-fill {{
      width: 100%;
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, {accent}, {secondary});
      transform-origin: right center;
    }}

    .teaser-hud-clip {{
      position: absolute;
      top: {sz_top + 6}px;
      left: 0;
      right: 0;
      z-index: 46;
      display: flex;
      justify-content: center;
      pointer-events: none;
    }}

    .teaser-pill-compact {{
      position: relative;
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 12px 24px 16px;
      border-radius: 999px;
      background: linear-gradient(90deg, {secondary}, {accent});
      color: #080a0f;
      font-size: 23px;
      font-weight: 900;
      box-shadow: 0 10px 28px rgba(0, 0, 0, 0.55);
      overflow: hidden;
    }}

    .teaser-mini-bar {{
      position: absolute;
      left: 0;
      right: 0;
      bottom: 0;
      height: 5px;
      background: rgba(8, 10, 15, 0.65);
      transform-origin: right center;
    }}

    /* Interactive Title Patches & Blur Masks */
    .ov-blur {{
      position: absolute;
      z-index: 35;
      border-radius: 14px;
      background: rgba(8, 12, 20, 0.72);
      pointer-events: none;
    }}

    .ov-patch {{
      position: absolute;
      z-index: 36;
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 12px 24px;
      color: #FFFFFF;
      font-weight: 900;
      line-height: 1.25;
      overflow: hidden;
      pointer-events: none;
    }}

    .ov-patch-text {{
      width: 100%;
      word-break: break-word;
      text-shadow: 0 3px 12px rgba(0, 0, 0, 0.65);
    }}

    .ov-style-solid_dark {{
      background: #0a0d16;
      border: 2.5px solid {accent};
      border-radius: 18px;
      box-shadow: 0 14px 36px rgba(0, 0, 0, 0.8);
    }}

    .ov-style-glass_gold {{
      background: rgba(10, 14, 24, 0.94);
      border: 2.5px solid {accent};
      border-radius: 20px;
      box-shadow: 0 16px 40px rgba(0, 0, 0, 0.72), 0 0 22px {hex_to_rgba(accent, 0.25)};
    }}

    .ov-style-cinema_bar {{
      background: linear-gradient(180deg, #06080e 0%, #0e1320 100%);
      border-top: 2px solid {hex_to_rgba(accent, 0.6)};
      border-bottom: 2px solid {hex_to_rgba(accent, 0.6)};
      border-radius: 6px;
    }}

    .ov-style-accent_pill {{
      background: {accent};
      color: #080a0f !important;
      border-radius: 999px;
      box-shadow: 0 14px 34px rgba(0, 0, 0, 0.6);
    }}

    .ov-style-accent_pill .ov-patch-text {{
      text-shadow: none;
    }}

    .ov-media {{
      position: absolute;
      z-index: 34;
      border-radius: 18px;
      overflow: hidden;
      border: 2.5px solid {accent};
      box-shadow: 0 16px 40px rgba(0, 0, 0, 0.72);
      pointer-events: none;
    }}

    .ov-media-el {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }}

    /* Callout Badge */
    .callout-clip {{
      position: absolute;
      top: {sz_top + 64}px;
      left: {sz_sides}px;
      right: {sz_sides}px;
      z-index: 28;
      display: flex;
      justify-content: center;
    }}

    .callout-card {{
      display: inline-flex;
      align-items: center;
      gap: 18px;
      padding: 14px 26px;
      border-radius: 20px;
      background: {surface_rgba};
      border: 2px solid {accent};
      box-shadow: 0 16px 40px rgba(0, 0, 0, 0.5);
    }}

    .callout-num {{
      font-family: "MontserratPro", sans-serif;
      font-size: 42px;
      font-weight: 900;
      color: #080a0f;
      background: {accent};
      padding: 4px 16px;
      border-radius: 14px;
    }}

    .callout-lbl {{
      color: {primary};
      font-size: 30px;
      font-weight: 800;
    }}

    /* B-Roll Card */
    .broll-clip {{
      position: absolute;
      top: {sz_top + 80}px;
      left: {sz_sides + 20}px;
      right: {sz_sides + 20}px;
      height: 510px;
      z-index: 27;
      display: flex;
      align-items: center;
      justify-content: center;
    }}

    .broll-card {{
      width: 100%;
      height: 100%;
      border-radius: 28px;
      overflow: hidden;
      border: 3px solid {accent};
      background: #080a0f;
      box-shadow: 0 24px 60px rgba(0, 0, 0, 0.65);
    }}

    .broll-media {{
      width: 100%;
      height: 100%;
      object-fit: cover;
    }}

    /* Pro RTL Captions + Karaoke + Emoji Pop */
    .cap-clip {{
      position: absolute;
      {cap_pos_css}
      left: {sz_sides}px;
      right: {sz_sides}px;
      z-index: 35;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 10px;
    }}

    .emoji-pop {{
      font-size: 62px;
      line-height: 1;
      text-shadow: 0 8px 18px rgba(0, 0, 0, 0.75);
    }}

    .cap-box {{
      max-width: 100%;
      padding: 14px 24px;
      border-radius: 20px;
      text-align: center;
      color: {primary};
      font-size: 46px;
      font-weight: 900;
      line-height: 1.32;
      overflow-wrap: break-word;
      text-shadow: 0 4px 16px rgba(0, 0, 0, 0.85);
    }}

    .cap-karaoke, .cap-chunk_highlight, .cap-word_by_word {{
      background: {surface_rgba};
      border: 1.5px solid rgba(255, 255, 255, 0.16);
      box-shadow: 0 14px 36px rgba(0, 0, 0, 0.52);
    }}

    .cap-box_bg {{
      background: {surface_rgba};
      border-right: 6px solid {accent};
      box-shadow: 0 16px 40px rgba(0, 0, 0, 0.55);
    }}

    .kw {{
      display: inline-block;
      margin: 0 11px;
      transform-origin: 50% 60%;
    }}

    .pw {{
      color: {accent};
      display: inline-block;
      text-shadow: 0 0 22px {hex_to_rgba(accent, 0.45)}, 0 4px 14px rgba(0,0,0,0.9);
    }}

    .cap-en-sub {{
      max-width: 94%;
      padding: 7px 20px;
      border-radius: 999px;
      background: rgba(8, 11, 19, 0.88);
      border: 1.5px solid {hex_to_rgba(accent, 0.45)};
      box-shadow: 0 10px 26px rgba(0, 0, 0, 0.55);
      color: #F1F5F9;
      font-family: "MontserratPro", "CairoPro", sans-serif;
      font-size: 27px;
      font-weight: 700;
      line-height: 1.28;
      letter-spacing: 0.25px;
      text-align: center;
      text-shadow: 0 2px 8px rgba(0, 0, 0, 0.9);
    }}

    /* CTA Outro Card */
    .cta-clip {{
      position: absolute;
      {cta_pos_css}
      left: {sz_sides}px;
      right: {sz_sides}px;
      z-index: 40;
      display: flex;
      justify-content: center;
    }}

    .cta-card {{
      position: relative;
      overflow: hidden;
      width: 100%;
      padding: 30px 34px;
      border-radius: 28px;
      background: linear-gradient(160deg, rgba(16, 20, 32, 0.95) 0%, rgba(8, 11, 18, 0.96) 100%);
      border: 3px solid {accent};
      box-shadow: 0 24px 60px rgba(0, 0, 0, 0.72), 0 0 36px {hex_to_rgba(accent, 0.28)}, inset 0 1.5px 0 rgba(255, 255, 255, 0.22);
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 14px;
      text-align: center;
    }}

    .card-shimmer {{
      position: absolute;
      inset: 0;
      width: 65%;
      background: linear-gradient(110deg, transparent 20%, rgba(255, 243, 176, 0.24) 50%, transparent 80%);
      pointer-events: none;
    }}

    /* Luxury Optional Salawat Ending Card */
    .salawat-card {{
      position: relative;
      overflow: hidden;
      width: 100%;
      padding: 34px 36px 30px;
      border-radius: 32px;
      background:
        radial-gradient(circle at 50% 0%, {hex_to_rgba(accent, 0.28)} 0%, rgba(11, 24, 22, 0.96) 52%, rgba(7, 11, 18, 0.98) 100%);
      border: 3px solid {accent};
      box-shadow:
        0 26px 68px rgba(0, 0, 0, 0.78),
        0 0 46px {hex_to_rgba(accent, 0.36)},
        inset 0 0 0 6px rgba(10, 16, 22, 0.85),
        inset 0 0 0 7.5px {hex_to_rgba(accent, 0.45)};
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 12px;
      text-align: center;
    }}

    .salawat-badge {{
      padding: 6px 24px;
      border-radius: 999px;
      background: linear-gradient(90deg, #FFF0A6, {accent});
      color: #080a0f;
      font-size: 24px;
      font-weight: 900;
      box-shadow: 0 6px 20px {hex_to_rgba(accent, 0.45)};
    }}

    .salawat-lead {{
      font-family: "AmiriPro", "CairoPro", serif;
      color: #F8FAFC;
      font-size: 44px;
      font-weight: 700;
      line-height: 1.3;
      text-shadow: 0 4px 16px rgba(0, 0, 0, 0.85);
    }}

    .salawat-main {{
      font-family: "AmiriPro", "CairoPro", serif;
      color: {accent};
      font-size: 62px;
      font-weight: 900;
      line-height: 1.24;
      text-shadow: 0 0 28px {hex_to_rgba(accent, 0.58)}, 0 6px 20px rgba(0, 0, 0, 0.92);
    }}

    .salawat-ornament {{
      width: 220px;
      height: 22px;
      margin: 2px 0;
    }}

    .salawat-sub {{
      font-size: 28px;
      font-weight: 800;
      color: #E2F5EA;
      text-shadow: 0 2px 10px rgba(0, 0, 0, 0.85);
    }}

    .salawat-handle {{
      margin-top: 4px;
      padding: 6px 22px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.10);
      border: 1.5px solid {hex_to_rgba(accent, 0.55)};
      color: #FFFFFF;
      font-size: 23px;
      font-weight: 800;
    }}

    .cta-logo {{
      width: 104px;
      height: 104px;
      object-fit: cover;
      border-radius: 50%;
      border: 3px solid {accent};
      box-shadow: 0 0 35px rgba(255, 214, 10, 0.45);
    }}

    .cta-text {{
      color: {primary};
      font-size: 42px;
      font-weight: 900;
      line-height: 1.35;
    }}

    .cta-handle {{
      padding: 8px 26px;
      border-radius: 999px;
      background: {accent};
      color: #080a0f;
      font-size: 28px;
      font-weight: 900;
    }}
{custom_css}
  </style>

  <div id="root" data-composition-id="reel" data-width="1080" data-height="1920">
    <div id="video-stage" class="video-stage">
      <video
        id="main-video"
        class="clip main-video"
        src="{source_video_rel}"
        data-start="0"
        data-duration="{round(duration, 3)}"
        data-has-audio="true"
        data-track-index="0"
      ></video>
    </div>

    <div class="cinema-vignette"></div>
    <div id="light-flash" class="light-flash"></div>

    <div class="progress-bar">
      <div class="progress-track">
        <div id="progress-fill" class="progress-fill"></div>
      </div>
      <div id="progress-tip" class="progress-tip"></div>
    </div>

{watermark_html}
    <div class="wave-pill">
{wave_bars_html}
    </div>

{hook_html}
{os.linesep.join(overlay_html_list)}
{os.linesep.join(callout_html_list)}
{os.linesep.join(broll_html_list)}
{os.linesep.join(caption_divs)}
{cta_html}
  </div>

  <script>
    const tl = gsap.timeline({{ paused: true }});
{prog_tween}
{hook_tweens}
{os.linesep.join(overlay_tweens)}
{os.linesep.join(zoom_tweens_list)}
{os.linesep.join(wave_tweens)}
{os.linesep.join(callout_tweens)}
{os.linesep.join(broll_tweens)}
{os.linesep.join(caption_tweens)}
{cta_tweens}
    window.__timelines["reel"] = tl;
  </script>
</template>
"""

    with open(os.path.join(comp_dir, "reel.html"), "w", encoding="utf-8") as f:
        f.write(reel_html)

    index_html = f"""<!doctype html>
<html lang="ar" dir="rtl">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1080, height=1920" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{
        width: 1080px;
        height: 1920px;
        overflow: hidden;
        background: #04060a;
      }}
      #root {{
        position: relative;
        width: 1080px;
        height: 1920px;
        overflow: hidden;
      }}
    </style>
  </head>
  <body>
    <div
      id="root"
      data-composition-id="main"
      data-start="0"
      data-duration="{round(duration, 3)}"
      data-width="1080"
      data-height="1920"
    >
      <div
        id="reel"
        data-composition-id="reel"
        data-composition-src="compositions/reel.html"
        data-track-kind="graphics"
        data-start="0"
        data-duration="{round(duration, 3)}"
        data-track-index="0"
        data-width="1080"
        data-height="1920"
      ></div>
    </div>
    <script>
      window.__timelines["main"] = gsap.timeline({{ paused: true }});
    </script>
  </body>
</html>
"""
    with open(os.path.join(hf_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    hf_json = os.path.join(hf_dir, "hyperframes.json")
    if not os.path.exists(hf_json):
        with open(hf_json, "w", encoding="utf-8") as f:
            json.dump({"fps": 30, "width": 1080, "height": 1920}, f, indent=2)

    cover_dir = os.path.join(project_dir, "work", "cover_project")
    cover_assets = os.path.join(cover_dir, "assets")
    os.makedirs(os.path.join(cover_assets, "fonts"), exist_ok=True)
    for font_name in ("Cairo-Variable.ttf", "Montserrat-Variable.ttf"):
        src_f = os.path.join(root_dir, "assets", "fonts", font_name)
        if os.path.exists(src_f):
            shutil.copy2(src_f, os.path.join(cover_assets, "fonts", font_name))
    frame_jpg = os.path.join(cover_assets, "frame.jpg")
    has_frame = extract_cover_frame(video_src_path, frame_jpg, duration)
    cover_headline = hook_title or settings.get("title") or account_name or "فيديو جديد"

    cover_logo_tag = ""
    if logo_file and os.path.exists(os.path.join(logo_dir, logo_file)):
        shutil.copy2(os.path.join(logo_dir, logo_file), os.path.join(cover_assets, logo_file))
        cover_logo_tag = f'<img src="assets/{logo_file}" class="cover-logo" alt="" />'

    cover_html = f"""<!doctype html>
<html lang="ar" dir="rtl">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1080, height=1920" />
    <style>
      @font-face {{
        font-family: "CairoPro";
        src: url("assets/fonts/Cairo-Variable.ttf") format("truetype");
        font-weight: 200 900;
      }}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{
        width: 1080px; height: 1920px; overflow: hidden;
        background: #080a0f; font-family: "CairoPro", sans-serif;
      }}
      #root {{
        position: relative; width: 1080px; height: 1920px; overflow: hidden;
      }}
      .bg-img {{
        position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover;
      }}
      .shade {{
        position: absolute; inset: 0;
        background: linear-gradient(180deg, rgba(6,8,14,0.45) 0%, rgba(6,8,14,0.22) 38%, rgba(6,8,14,0.85) 75%, rgba(6,8,14,0.96) 100%);
      }}
      .grid-safe {{
        position: absolute;
        top: 285px; bottom: 285px; left: 90px; right: 90px;
        display: flex; flex-direction: column;
        justify-content: flex-end; align-items: center;
        text-align: center; gap: 28px; padding-bottom: 46px;
      }}
      .pill {{
        display: inline-flex; align-items: center; gap: 14px;
        padding: 10px 32px 10px 16px; border-radius: 999px;
        background: {accent}; color: #080a0f;
        font-size: 32px; font-weight: 900;
        box-shadow: 0 12px 32px rgba(0,0,0,0.45);
      }}
      .cover-logo {{
        width: 52px; height: 52px; border-radius: 50%;
        border: 2px solid #080a0f; object-fit: cover;
      }}
      .title {{
        color: {primary};
        font-size: 86px; font-weight: 900; line-height: 1.22;
        text-shadow: 0 8px 28px rgba(0,0,0,0.85);
      }}
      .pw {{ color: {accent}; }}
      .bar {{
        width: 180px; height: 10px; border-radius: 999px; background: {accent};
      }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="cover" data-start="0" data-duration="1" data-width="1080" data-height="1920" data-no-timeline>
      {"<img src='assets/frame.jpg' class='bg-img' alt='' />" if has_frame else ""}
      <div class="shade"></div>
      <div class="grid-safe">
        <div class="pill">
          {cover_logo_tag}
          <span>{html.escape(account_name or "غناوي هلنا")}</span>
        </div>
        <h1 class="title">{format_rtl_html(cover_headline)}</h1>
        <div class="bar"></div>
      </div>
    </div>
  </body>
</html>
"""
    with open(os.path.join(cover_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(cover_html)

    cues_path = os.path.join(project_dir, "work", "sfx_cues.json")
    with open(cues_path, "w", encoding="utf-8") as f:
        json.dump(sfx_cues, f, ensure_ascii=False, indent=2)

    return {
        "hf_dir": hf_dir,
        "cover_dir": cover_dir,
        "sfx_cues_path": cues_path,
        "source_video_name": source_video_name,
        "visual_sig": hashlib.sha1((source_video_name + "\n" + reel_html).encode("utf-8")).hexdigest()[:16],
        "cover_sig": hashlib.sha1((source_video_name + "\n" + cover_html).encode("utf-8")).hexdigest()[:16],
        "duration": duration,
        "caption_count": len(caption_divs),
        "broll_count": broll_idx,
        "callout_count": len(callouts),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build HyperFrames reel + cover projects.")
    parser.add_argument("project_dir", help="Video project directory (e.g. videos/01-first-video)")
    parser.add_argument("--video", required=True, help="Source cut/graded MP4 path")
    parser.add_argument("--timeline", required=True, help="Path to work/timeline_data.json")
    args = parser.parse_args()

    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    brand_path = os.path.join(root_dir, "studio", "brand-config.json")
    settings_path = os.path.join(args.project_dir, "settings.json")

    with open(brand_path, "r", encoding="utf-8-sig") as f:
        brand = json.load(f)
    with open(settings_path, "r", encoding="utf-8-sig") as f:
        settings = json.load(f)
    with open(args.timeline, "r", encoding="utf-8-sig") as f:
        timeline = json.load(f)

    info = build_project(root_dir, args.project_dir, brand, settings, timeline, args.video)
    print(json.dumps(info, ensure_ascii=False))


if __name__ == "__main__":
    main()
