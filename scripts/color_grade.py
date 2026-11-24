"""
100% Free Repeatable Color Grading + 9:16 Vertical Framing using FFmpeg.

Presets:
  - natural      : Subtle contrast + clarity boost (clean everyday look)
  - warm_creator : Slight warmth, punchy contrast, rich skin tones (Reels/TikTok)
  - crisp_edu    : Bright, clean, slightly cool clarity (tutorials/education)
  - cinematic    : Moody contrast, gentle teal-warm balance (storytelling)
  - lut          : Apply any free .cube 3D LUT file via --lut path/to/look.cube

Usage:
  python scripts/color_grade.py input.mp4 graded.mp4 --preset warm_creator
  python scripts/color_grade.py input.mp4 graded.mp4 --preset crisp_edu --vertical
  python scripts/color_grade.py input.mp4 graded.mp4 --lut assets/luts/my_look.cube --vertical
"""

import argparse
import shutil
import subprocess
import sys


COLOR_PRESETS = {
    "natural": "eq=contrast=1.05:brightness=0.01:saturation=1.06,unsharp=3:3:0.4:3:3:0.0",
    "warm_creator": "eq=contrast=1.08:brightness=0.015:saturation=1.12,colorbalance=rs=0.03:gs=0.01:bs=-0.03:rm=0.02:bm=-0.02,unsharp=3:3:0.5:3:3:0.0",
    "crisp_edu": "eq=contrast=1.07:brightness=0.02:saturation=1.05,colorbalance=rs=-0.01:bs=0.02,unsharp=5:5:0.6:3:3:0.0",
    "cinematic": "eq=contrast=1.12:brightness=-0.01:saturation=0.95,colorbalance=rs=-0.03:gs=0.0:bs=0.04:rh=0.03:gh=0.01:bh=-0.02,unsharp=3:3:0.4:3:3:0.0",
}


def escape_lut_path(path: str) -> str:
    # FFmpeg lut3d filter requires escaped backslashes and colons on Windows
    return path.replace("\\", "/").replace(":", "\\:")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Apply color grading preset or LUT and optional 9:16 crop.")
    parser.add_argument("input", help="Input video file")
    parser.add_argument("output", help="Output video file")
    parser.add_argument(
        "--preset",
        choices=list(COLOR_PRESETS.keys()),
        default="natural",
        help="Color preset (default: natural)",
    )
    parser.add_argument("--lut", help="Optional .cube 3D LUT file path (overrides --preset)")
    parser.add_argument(
        "--vertical",
        action="store_true",
        help="Reframe and scale cleanly to 1080x1920 (9:16)",
    )
    parser.add_argument(
        "--fit-mode",
        choices=["cover", "blur_bg"],
        default="cover",
        help="9:16 framing mode: cover (fill screen) or blur_bg (blurred cinema frame)",
    )
    parser.add_argument("--zoom", type=float, default=1.0, help="Crop zoom factor (1.0 - 2.0)")
    parser.add_argument("--pan-x", type=float, default=0.0, help="Horizontal pan percent (-50 to 50)")
    parser.add_argument("--pan-y", type=float, default=0.0, help="Vertical pan percent (-50 to 50)")
    parser.add_argument("--crop-top", type=float, default=0.0, help="Trim percentage from top edge (0 - 45)")
    parser.add_argument("--crop-bottom", type=float, default=0.0, help="Trim percentage from bottom edge (0 - 45)")
    parser.add_argument("--crop-left", type=float, default=0.0, help="Trim percentage from left edge (0 - 45)")
    parser.add_argument("--crop-right", type=float, default=0.0, help="Trim percentage from right edge (0 - 45)")
    parser.add_argument("--crf", type=int, default=18, help="H.264 CRF quality (lower=better, default: 18)")
    parser.add_argument("--fast", action="store_true", help="Use veryfast x264 preset for intermediate work files")
    parser.add_argument("--preview", action="store_true", help="Fast 540x960 ultrafast preview output")
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        print("ERROR: ffmpeg not found in PATH.", file=sys.stderr)
        sys.exit(1)

    zoom = max(1.0, min(2.0, float(args.zoom)))
    pan_x = max(-50.0, min(50.0, float(args.pan_x)))
    pan_y = max(-50.0, min(50.0, float(args.pan_y)))
    crop_top = max(0.0, min(45.0, float(args.crop_top)))
    crop_bottom = max(0.0, min(45.0, float(args.crop_bottom)))
    crop_left = max(0.0, min(45.0, float(args.crop_left)))
    crop_right = max(0.0, min(45.0, float(args.crop_right)))

    out_w, out_h = (540, 960) if args.preview else (1080, 1920)

    pre_crop = ""
    if crop_top > 0.0 or crop_bottom > 0.0 or crop_left > 0.0 or crop_right > 0.0:
        top_f = crop_top / 100.0
        bot_f = crop_bottom / 100.0
        left_f = crop_left / 100.0
        right_f = crop_right / 100.0
        keep_w = max(0.20, 1.0 - left_f - right_f)
        keep_h = max(0.20, 1.0 - top_f - bot_f)
        pre_crop = (
            f"crop=trunc(iw*{keep_w:.4f}/2)*2:trunc(ih*{keep_h:.4f}/2)*2:"
            f"trunc(iw*{left_f:.4f}/2)*2:trunc(ih*{top_f:.4f}/2)*2"
        )

    color_filter = "" if args.preview else (f"lut3d='{escape_lut_path(args.lut)}'" if args.lut else COLOR_PRESETS[args.preset])
    preset = "ultrafast" if args.preview else ("superfast" if args.fast else "medium")
    crf = str(28 if args.preview else args.crf)
    gop_args = ["-g", "30", "-keyint_min", "30"] if not args.preview else []

    if args.vertical and args.fit_mode == "blur_bg":
        fg_w = max(160, int(round(out_w * zoom / 2) * 2))
        fg_h = max(160, int(round(out_h * zoom / 2) * 2))
        pre = (pre_crop + ",") if pre_crop else ""
        color_tail = ("," + color_filter) if color_filter else ""
        # Downscale -> fast boxblur -> bilinear upscale: ~30x faster than full-res gblur with smoother cinema blur
        filter_complex = (
            f"[0:v]{pre}split=2[bg0][fg0];"
            f"[bg0]scale=135:240:force_original_aspect_ratio=increase,crop=135:240,"
            f"boxblur=6:2,scale={out_w}:{out_h}:flags=bilinear,"
            f"eq=brightness=-0.12:saturation=0.9[bg];"
            f"[fg0]scale={fg_w}:{fg_h}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=x=(W-w)/2+({pan_x:.4f}/100)*W*0.35:"
            f"y=(H-h)/2+({pan_y:.4f}/100)*H*0.35:shortest=1,"
            f"crop={out_w}:{out_h}:0:0,setsar=1{color_tail}[vout]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", args.input,
            "-filter_complex", filter_complex,
            "-map", "[vout]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", preset, "-crf", crf,
            *gop_args,
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
            args.output,
        ]
    else:
        vfilters = []
        if pre_crop:
            vfilters.append(pre_crop)
        if args.vertical:
            sw = max(out_w, int(round(out_w * zoom / 2) * 2))
            sh = max(out_h, int(round(out_h * zoom / 2) * 2))
            px = max(0.0, min(1.0, (pan_x + 50.0) / 100.0))
            py = max(0.0, min(1.0, (pan_y + 50.0) / 100.0))
            vfilters.append(
                f"scale={sw}:{sh}:force_original_aspect_ratio=increase,"
                f"crop={out_w}:{out_h}:max(0\\,min(iw-{out_w}\\,(iw-{out_w})*{px:.4f})):"
                f"max(0\\,min(ih-{out_h}\\,(ih-{out_h})*{py:.4f})),setsar=1"
            )
        if color_filter:
            vfilters.append(color_filter)
        cmd = [
            "ffmpeg", "-y",
            "-i", args.input,
            "-vf", ",".join(vfilters) if vfilters else "null",
            "-c:v", "libx264", "-preset", preset, "-crf", crf,
            *gop_args,
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
            args.output,
        ]

    print(f"Applying color grading ({args.lut or args.preset})...")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        print("FFmpeg color grading failed:\n", res.stderr, file=sys.stderr)
        sys.exit(res.returncode)
    print(f"Done! Graded video saved to: {args.output}")


if __name__ == "__main__":
    main()

