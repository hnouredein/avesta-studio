"""
Generate clean, 100% royalty-free procedural SFX WAV files for Reels/TikTok/Shorts.
Zero external dependencies (Python standard library only).
"""

import math
import os
import random
import struct
import wave

SAMPLE_RATE = 44100


def write_wav(path: str, samples: list[float]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    peak = max((abs(s) for s in samples), default=1.0)
    scale = 0.85 / peak if peak > 0 else 1.0
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for s in samples:
            val = max(-1.0, min(1.0, s * scale))
            frames.extend(struct.pack("<h", int(val * 32767)))
        wf.writeframes(bytes(frames))


def lowpass(samples: list[float], cutoff_hz: float) -> list[float]:
    rc = 1.0 / (2.0 * math.pi * cutoff_hz)
    dt = 1.0 / SAMPLE_RATE
    alpha = dt / (rc + dt)
    out = []
    prev = 0.0
    for s in samples:
        prev = prev + alpha * (s - prev)
        out.append(prev)
    return out


def make_pop(duration: float = 0.12) -> list[float]:
    """Crisp UI pop for captions, icons, and badges."""
    n = int(SAMPLE_RATE * duration)
    samples = []
    phase = 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        # Pitch drops quickly from 620Hz to 190Hz
        freq = 190.0 + 430.0 * math.exp(-t * 38.0)
        phase += 2.0 * math.pi * freq / SAMPLE_RATE
        env = math.sin(min(1.0, t / 0.008) * math.pi / 2.0) * math.exp(-t * 32.0)
        samples.append(math.sin(phase) * env)
    return samples


def make_click(duration: float = 0.06) -> list[float]:
    """Subtle tactile click for checklist items or counter ticks."""
    n = int(SAMPLE_RATE * duration)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = math.exp(-t * 95.0)
        tone = math.sin(2.0 * math.pi * 1200.0 * t) * 0.6 + math.sin(2.0 * math.pi * 2400.0 * t) * 0.4
        samples.append(tone * env)
    return samples


def make_whoosh(duration: float = 0.35) -> list[float]:
    """Smooth air whoosh for hook entrance and scene transitions."""
    rng = random.Random(42)
    n = int(SAMPLE_RATE * duration)
    noise = [rng.uniform(-1.0, 1.0) for _ in range(n)]
    # Two-pass smoothing for warm air swoosh
    smooth = lowpass(lowpass(noise, 1400.0), 1100.0)
    samples = []
    for i in range(n):
        u = i / n
        # Smooth bell envelope peaking at 42%
        env = (math.sin(math.pi * (u ** 0.85)) ** 1.8)
        # Add subtle sub body
        t = i / SAMPLE_RATE
        sub = math.sin(2.0 * math.pi * (90.0 + 130.0 * u) * t) * 0.15
        samples.append((smooth[i] * 2.2 + sub) * env)
    return samples


def make_riser(duration: float = 0.75) -> list[float]:
    """Gentle tension riser leading into a key point or CTA."""
    rng = random.Random(7)
    n = int(SAMPLE_RATE * duration)
    noise = lowpass([rng.uniform(-1.0, 1.0) for _ in range(n)], 1800.0)
    samples = []
    phase = 0.0
    for i in range(n):
        u = i / n
        freq = 180.0 + 520.0 * (u ** 2.0)
        phase += 2.0 * math.pi * freq / SAMPLE_RATE
        env = (u ** 2.2) * (1.0 - max(0.0, (u - 0.92) / 0.08))
        samples.append((math.sin(phase) * 0.45 + noise[i] * 0.8) * env)
    return samples


def make_chime(duration: float = 0.45) -> list[float]:
    """Warm subtle notification chime for tips or key takeaways."""
    n = int(SAMPLE_RATE * duration)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = math.sin(min(1.0, t / 0.01) * math.pi / 2.0) * math.exp(-t * 8.5)
        s = (
            math.sin(2.0 * math.pi * 587.33 * t) * 0.55  # D5
            + math.sin(2.0 * math.pi * 880.00 * t) * 0.35  # A5
            + math.sin(2.0 * math.pi * 1174.66 * t) * 0.15  # D6
        )
        samples.append(s * env)
    return samples


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sfx_dir = os.path.join(root, "assets", "sfx")
    generators = {
        "pop.wav": make_pop,
        "click.wav": make_click,
        "whoosh.wav": make_whoosh,
        "riser.wav": make_riser,
        "chime.wav": make_chime,
    }
    for filename, fn in generators.items():
        out_path = os.path.join(sfx_dir, filename)
        write_wav(out_path, fn())
        print(f"Generated: {out_path}")


if __name__ == "__main__":
    main()

