"""Download one or many source videos and join them into a single input.mp4.

Usage: fetch_sources.py "<url1> <url2> ..." OUT.mp4
URLs may be separated by whitespace, commas or newlines. One URL = same as download_url.py.
Several URLs = each clip is downloaded (TikTok/Instagram/YouTube/direct), normalised to the
first clip's size at 30 fps with 48 kHz stereo audio (silent audio added when missing) and
concatenated in order.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", path],
        capture_output=True, text=True, check=True,
    ).stdout
    streams = json.loads(out).get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    has_a = any(s.get("codec_type") == "audio" for s in streams)
    return int(v.get("width", 1080)), int(v.get("height", 1920)), has_a


def main():
    raw, out = sys.argv[1], sys.argv[2]
    urls = [u for u in re.split(r"[\s,]+", raw.strip()) if u]
    if not urls:
        sys.exit("no source url")
    dl = os.path.join(HERE, "download_url.py")
    if len(urls) == 1:
        run([sys.executable, dl, urls[0], out])
        return
    workdir = os.path.join(os.path.dirname(out) or ".", "clips")
    os.makedirs(workdir, exist_ok=True)
    raws = []
    for i, u in enumerate(urls, 1):
        p = os.path.join(workdir, f"raw{i}.mp4")
        print(f"== clip {i}/{len(urls)}: {u}", flush=True)
        run([sys.executable, dl, u, p])
        raws.append(p)
    w, h, _ = probe(raws[0])
    w -= w % 2
    h -= h % 2
    norm = []
    for i, p in enumerate(raws, 1):
        n = os.path.join(workdir, f"norm{i}.mp4")
        _, _, has_a = probe(p)
        vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
              f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30,format=yuv420p")
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", p]
        if not has_a:
            cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest"]
        cmd += ["-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
                "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k", "-movflags", "+faststart", n]
        run(cmd)
        norm.append(n)
    lst = os.path.join(workdir, "list.txt")
    with open(lst, "w") as f:
        for n in norm:
            f.write(f"file '{os.path.abspath(n)}'\n")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
         "-movflags", "+faststart", out])
    import shutil
    shutil.rmtree(workdir, ignore_errors=True)
    print(f"joined {len(urls)} clips -> {out}", flush=True)


if __name__ == "__main__":
    main()
