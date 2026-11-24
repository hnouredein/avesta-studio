"""
Mix a video's voice track with background music (with real Auto-Ducking)
and optional timed SFX cues using FFmpeg (100% free, local).

Usage:
  # Background music only with auto-ducking:
  python scripts/mix_audio.py video.mp4 output.mp4 --music assets/music/bg.mp3

  # Background music + SFX cue JSON file:
  python scripts/mix_audio.py video.mp4 output.mp4 --music assets/music/bg.mp3 --sfx-cues cues.json

Example cues.json:
  [
    {"file": "assets/sfx/whoosh.wav", "time": 0.0, "volume_db": -12},
    {"file": "assets/sfx/pop.wav", "time": 4.2, "volume_db": -14},
    {"file": "assets/sfx/riser.wav", "time": 26.5, "volume_db": -13}
  ]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys


def get_duration(path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {res.stderr}")
    return float(res.stdout.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Mix background music (auto-ducked) and SFX into a video.")
    parser.add_argument("input", help="Input video file with voice track")
    parser.add_argument("output", help="Output video file")
    parser.add_argument("--music", help="Optional background music track (mp3/wav)")
    parser.add_argument("--music-db", type=float, default=-22.0, help="Base music volume in dB (default: -22)")
    parser.add_argument("--fade-out", type=float, default=1.5, help="Music fade-out duration in seconds (default: 1.5)")
    parser.add_argument("--sfx-cues", help="Optional JSON file listing SFX cues [{file, time, volume_db}]")
    parser.add_argument("--no-duck", action="store_true", help="Disable sidechain auto-ducking")
    parser.add_argument("--voice-track", help="Optional external voiceover or TTS audio file")
    parser.add_argument("--mute-original", action="store_true", help="Mute the video's original audio track")
    parser.add_argument("--original-db", type=float, default=0.0, help="Original audio gain in dB (default: 0)")
    parser.add_argument("--voice-db", type=float, default=0.0, help="External voice track gain in dB (default: 0)")
    args = parser.parse_args()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("ERROR: ffmpeg/ffprobe not found in PATH.", file=sys.stderr)
        sys.exit(1)

    cues = []
    if args.sfx_cues:
        with open(args.sfx_cues, "r", encoding="utf-8-sig") as f:
            cues = json.load(f)

    has_voice_track = bool(args.voice_track and os.path.exists(args.voice_track))
    if not args.music and not cues and not has_voice_track and not args.mute_original and args.original_db == 0.0:
        print("Nothing to mix (--music, --sfx-cues, or --voice-track required). Copying input.")
        shutil.copy2(args.input, args.output)
        return

    duration = get_duration(args.input)
    cmd = ["ffmpeg", "-y", "-i", args.input]
    filter_parts = []
    mix_inputs = []
    next_idx = 1

    # Original video audio stream (kept as first stream so amix duration=first always matches video duration)
    orig_vol = "0" if args.mute_original else f"{args.original_db}dB"
    if args.music and not args.no_duck and not has_voice_track and not args.mute_original:
        filter_parts.append(
            f"[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"volume={orig_vol},asplit=2[orig_main][voice_sc]"
        )
    else:
        filter_parts.append(
            f"[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"volume={orig_vol}[orig_main]"
        )
    mix_inputs.append("[orig_main]")

    # External voiceover or AI TTS track
    if has_voice_track:
        cmd.extend(["-i", args.voice_track])
        v_idx = next_idx
        next_idx += 1
        if args.music and not args.no_duck:
            filter_parts.append(
                f"[{v_idx}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
                f"atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,volume={args.voice_db}dB,"
                f"asplit=2[ext_voice][voice_sc]"
            )
        else:
            filter_parts.append(
                f"[{v_idx}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
                f"atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,volume={args.voice_db}dB[ext_voice]"
            )
        mix_inputs.append("[ext_voice]")

    # Prepare background music (looped to video duration, lowered, faded, and sidechain-ducked)
    if args.music:
        cmd.extend(["-stream_loop", "-1", "-i", args.music])
        music_idx = next_idx
        next_idx += 1
        fade_start = max(0.0, duration - args.fade_out)
        music_chain = (
            f"[{music_idx}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,"
            f"volume={args.music_db}dB,"
            f"afade=t=in:st=0:d=0.6,afade=t=out:st={fade_start:.3f}:d={args.fade_out:.3f}[music_pre]"
        )
        filter_parts.append(music_chain)

        if not args.no_duck and (has_voice_track or not args.mute_original):
            # Sidechain compressor ducks music whenever speaker is talking
            filter_parts.append(
                "[music_pre][voice_sc]sidechaincompress=threshold=0.03:ratio=6:attack=25:release=350:makeup=1[music_ducked]"
            )
            mix_inputs.append("[music_ducked]")
        else:
            mix_inputs.append("[music_pre]")

    # Prepare timed SFX cues
    for i, cue in enumerate(cues):
        sfx_path = cue["file"]
        if not os.path.exists(sfx_path):
            print(f"WARNING: SFX file not found, skipping: {sfx_path}", file=sys.stderr)
            continue
        cmd.extend(["-i", sfx_path])
        idx = next_idx
        next_idx += 1
        delay_ms = max(0, int(round(float(cue.get("time", 0.0)) * 1000)))
        vol_db = float(cue.get("volume_db", -12.0))
        label = f"sfx_{i}"
        filter_parts.append(
            f"[{idx}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"volume={vol_db}dB,adelay={delay_ms}|{delay_ms}[{label}]"
        )
        mix_inputs.append(f"[{label}]")

    # Combine all audio streams with amix (normalize=0 preserves our exact dB balances) + soft limiter
    mix_str = "".join(mix_inputs)
    filter_parts.append(
        f"{mix_str}amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=2:normalize=0,"
        f"alimiter=limit=0.95[aout]"
    )

    filter_complex = ";".join(filter_parts)
    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-shortest",
        "-movflags", "+faststart",
        args.output,
    ])

    print(f"Mixing audio ({len(mix_inputs)} streams)...")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        print("FFmpeg mix failed:\n", res.stderr, file=sys.stderr)
        sys.exit(res.returncode)
    print(f"Done! Mixed video saved to: {args.output}")


if __name__ == "__main__":
    main()
