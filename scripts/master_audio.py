"""
100% Free Studio Audio Mastering for Talking-Head Videos using FFmpeg.
Pipeline:
  1. High-pass filter (80Hz) to cut low-end rumble / mic handling noise.
  2. Gentle FFT noise reduction (afftdn) to reduce room hiss without metallic artifacts.
  3. Voice clarity EQ (subtle warmth + presence boost around 3.2kHz).
  4. Dynamic range compression (acompressor) for consistent vocal volume.
  5. Loudness normalization (loudnorm to -14 LUFS, -1.5 dBTP) — Reels/TikTok/Shorts standard.

Usage:
  python scripts/master_audio.py input.mp4 output_mastered.mp4
  python scripts/master_audio.py input.mp4 output_mastered.mp4 --denoise medium
  python scripts/master_audio.py input.mp4 output_voice.wav --audio-only
"""

import argparse
import shutil
import subprocess
import sys


DENOISE_PRESETS = {
    "off": None,
    "light": "afftdn=nr=8:nf=-30:tn=1",
    "medium": "afftdn=nr=12:nf=-25:tn=1",
    "strong": "afftdn=nr=18:nf=-22:tn=1",
}


VOICE_PRESETS = {
    "studio": [
        "highpass=f=80",
        "equalizer=f=250:t=q:w=1.2:g=-1.8",
        "equalizer=f=3200:t=q:w=1.4:g=2.2",
        "acompressor=threshold=-20dB:ratio=3:attack=10:release=120:makeup=2",
    ],
    "podcast": [
        "highpass=f=70",
        "equalizer=f=120:t=q:w=1.0:g=3.0",
        "equalizer=f=280:t=q:w=1.2:g=-2.2",
        "equalizer=f=3500:t=q:w=1.3:g=2.8",
        "acompressor=threshold=-22dB:ratio=4:attack=8:release=140:makeup=3",
    ],
    "heritage_reverb": [
        "highpass=f=80",
        "equalizer=f=220:t=q:w=1.1:g=1.5",
        "equalizer=f=3000:t=q:w=1.4:g=1.8",
        "acompressor=threshold=-20dB:ratio=2.8:attack=12:release=150:makeup=2",
        "aecho=0.8:0.88:42:0.16",
    ],
    "cinema": [
        "highpass=f=65",
        "equalizer=f=160:t=q:w=1.0:g=2.4",
        "equalizer=f=4500:t=q:w=1.5:g=1.4",
        "acompressor=threshold=-19dB:ratio=2.5:attack=15:release=160:makeup=2",
    ],
    "raw": [],
}


def build_filter_chain(denoise: str, lufs: float, true_peak: float, preset: str = "studio") -> str:
    if preset == "raw":
        return f"loudnorm=I={lufs}:TP={true_peak}:LRA=11"
    chain = VOICE_PRESETS.get(preset, VOICE_PRESETS["studio"])
    filters = [chain[0]] if chain else ["highpass=f=80"]
    dn = DENOISE_PRESETS.get(denoise)
    if dn:
        filters.append(dn)
    filters.extend(chain[1:])
    # Broadcast / social media loudness normalization
    filters.append(f"loudnorm=I={lufs}:TP={true_peak}:LRA=11")
    return ",".join(filters)


def main() -> None:
    parser = argparse.ArgumentParser(description="Studio audio mastering via FFmpeg.")
    parser.add_argument("input", help="Input video or audio file path")
    parser.add_argument("output", help="Output video or audio file path")
    parser.add_argument(
        "--denoise",
        choices=["off", "light", "medium", "strong"],
        default="light",
        help="Noise reduction intensity (default: light)",
    )
    parser.add_argument(
        "--preset",
        choices=list(VOICE_PRESETS.keys()),
        default="studio",
        help="Voice processing preset (default: studio)",
    )
    parser.add_argument("--lufs", type=float, default=-14.0, help="Target LUFS (default: -14.0)")
    parser.add_argument("--tp", type=float, default=-1.5, help="True peak dBTP (default: -1.5)")
    parser.add_argument("--audio-only", action="store_true", help="Export mastered audio only (WAV/AAC)")
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        print("ERROR: ffmpeg not found in PATH.", file=sys.stderr)
        sys.exit(1)

    af = build_filter_chain(args.denoise, args.lufs, args.tp, args.preset)
    cmd = ["ffmpeg", "-y", "-i", args.input, "-af", af]

    if args.audio_only:
        cmd.extend(["-vn", "-ar", "48000", "-ac", "2", args.output])
    else:
        cmd.extend(["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", args.output])

    print("Running audio mastering...")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        print("FFmpeg failed:\n", res.stderr, file=sys.stderr)
        sys.exit(res.returncode)
    print(f"Done! Mastered file saved to: {args.output}")


if __name__ == "__main__":
    main()

