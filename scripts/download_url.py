"""
Direct URL & Social Media Video Downloader powered by yt-dlp + direct HTTP fallback.

Downloads a video from TikTok, Facebook, Instagram Reels, YouTube Shorts, or direct MP4 URL,
remuxes/transcodes to faststart H.264 MP4 when needed, and prints structured lines:
  @DL <pct> <label>
  @RESULT {"ok": true, "title": "...", "size": <bytes>, "path": "..."}
"""

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def sanitize_title(raw: str | None, url: str) -> str:
    text = (raw or "").strip()
    if not text:
        parsed = urllib.parse.urlparse(url)
        tail = os.path.basename(parsed.path.rstrip("/"))
        text = os.path.splitext(urllib.parse.unquote(tail))[0] or parsed.netloc or "video"
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return (text[:80] or "video").strip()


def clean_temp_files(work_dir: str) -> None:
    for p in glob.glob(os.path.join(work_dir, "dl_temp.*")):
        try:
            os.remove(p)
        except OSError:
            pass


def emit_dl(pct: int, msg: str) -> None:
    clamped = max(0, min(100, int(pct)))
    print(f"@DL {clamped} {msg}", flush=True)


def download_direct_http(url: str, temp_base: str) -> tuple[str, str]:
    """Stream direct HTTP/HTTPS media links or HLS (.m3u8) streams when yt-dlp rejects as Unsupported URL."""
    parsed = urllib.parse.urlparse(url)
    ext = os.path.splitext(parsed.path)[1].lower()
    if ext == ".m3u8" or ".m3u8" in url.lower():
        temp_path = f"{temp_base}.mp4"
        emit_dl(15, "📡 جاري سحب بث الفيديو (HLS/M3U8) وتحويله إلى MP4...")
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-i", url,
                "-c", "copy", "-bsf:a", "aac_adtstoasc", "-movflags", "+faststart",
                temp_path,
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if proc.returncode != 0 or not os.path.exists(temp_path) or os.path.getsize(temp_path) <= 1024:
            proc2 = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", url,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                    temp_path,
                ],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if proc2.returncode != 0 or not os.path.exists(temp_path):
                raise RuntimeError(f"فشل سحب رابط البث M3U8: {proc2.stderr[:220]}")
        emit_dl(97, "⚙️ تم سحب الفيديو بنجاح...")
        return temp_path, sanitize_title(None, url)

    if ext not in (".mp4", ".mov", ".webm", ".mkv", ".m4v"):
        ext = ".mp4"
    temp_path = f"{temp_base}{ext}"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            )
        },
    )
    emit_dl(2, "⬇️ جاري التحميل المباشر من الرابط... 2%")
    last_emit_t = time.monotonic()
    last_emit_pct = 2
    downloaded = 0

    with urllib.request.urlopen(req, timeout=45) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        with open(temp_path, "wb") as out_f:
            while True:
                chunk = resp.read(262144)
                if not chunk:
                    break
                out_f.write(chunk)
                downloaded += len(chunk)
                now = time.monotonic()
                pct = int(min(96, (downloaded * 96 / total))) if total > 0 else min(90, last_emit_pct + 5)
                if pct - last_emit_pct >= 5 or (now - last_emit_t) >= 0.7:
                    emit_dl(pct, f"⬇️ جاري التحميل المباشر... {pct}%")
                    last_emit_t = now
                    last_emit_pct = pct

    emit_dl(97, "⚙️ جاري تجهيز ملف الفيديو...")
    return temp_path, sanitize_title(None, url)


def download_with_ytdlp(
    url: str,
    work_dir: str,
    cookies_file: str | None = None,
    cookies_browser: str | None = None,
) -> tuple[str, str]:
    import yt_dlp

    temp_base = os.path.join(work_dir, "dl_temp")
    state: dict[str, Any] = {"last_t": 0.0, "last_pct": -1}

    def hook(d: dict[str, Any]) -> None:
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            dl = d.get("downloaded_bytes") or 0
            pct = int(min(95, (dl * 95 / total))) if total > 0 else min(90, max(5, state["last_pct"] + 4))
            now = time.monotonic()
            if pct - state["last_pct"] >= 5 or (now - state["last_t"]) >= 0.6:
                speed_str = (d.get("_speed_str") or "").strip()
                extra = f" ({speed_str})" if speed_str else ""
                emit_dl(pct, f"⬇️ جاري التحميل... {pct}%{extra}")
                state["last_t"] = now
                state["last_pct"] = pct
        elif status == "finished":
            emit_dl(96, "⚙️ جاري دمج وتجهيز صيغة MP4...")

    ydl_opts: dict[str, Any] = {
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
        "outtmpl": f"{temp_base}.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "progress_hooks": [hook],
    }
    if shutil.which("node"):
        ydl_opts["js_runtimes"] = {"node": {}}
    if cookies_file and os.path.exists(cookies_file):
        ydl_opts["cookiefile"] = cookies_file
    elif cookies_browser and cookies_browser in ("firefox", "edge", "chrome", "brave", "opera", "vivaldi"):
        ydl_opts["cookiesfrombrowser"] = (cookies_browser,)

    emit_dl(2, "⬇️ جاري جلب بيانات الفيديو من الرابط...")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    title = sanitize_title(info.get("title") if isinstance(info, dict) else None, url)
    downloaded_file: str | None = None
    if isinstance(info, dict):
        req_dls = info.get("requested_downloads") or []
        if req_dls and isinstance(req_dls[0], dict):
            cand = req_dls[0].get("filepath")
            if cand and os.path.exists(cand):
                downloaded_file = cand
        if not downloaded_file:
            cand = ydl.prepare_filename(info) if info else None
            if cand and os.path.exists(cand):
                downloaded_file = cand

    if not downloaded_file or not os.path.exists(downloaded_file):
        candidates = [
            p
            for p in glob.glob(os.path.join(work_dir, "dl_temp.*"))
            if not p.endswith((".part", ".ytdl", ".temp"))
        ]
        if candidates:
            downloaded_file = max(candidates, key=os.path.getsize)

    if not downloaded_file or not os.path.exists(downloaded_file):
        raise RuntimeError("لم يتم العثور على ملف الفيديو بعد التحميل.")

    return downloaded_file, title


def ensure_mp4(src_path: str, dest_mp4: str) -> None:
    ext = os.path.splitext(src_path)[1].lower()
    if ext == ".mp4":
        shutil.move(src_path, dest_mp4)
        return

    emit_dl(98, "🎞️ جاري تحويل الصيغة إلى MP4...")
    proc = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", src_path,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            dest_mp4,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        os.remove(src_path)
    except OSError:
        pass
    if proc.returncode != 0 or not os.path.exists(dest_mp4):
        raise RuntimeError(f"فشل تحويل الصيغة إلى MP4: {proc.stderr[:260]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download social/direct video URL to MP4.")
    parser.add_argument("url", help="HTTP/HTTPS video URL")
    parser.add_argument("dest_mp4", help="Destination input.mp4 path")
    parser.add_argument("--cookies", help="Optional user-exported Netscape cookies.txt file for authenticated downloads")
    parser.add_argument("--cookies-browser", help="Optional user-selected browser name for yt-dlp --cookies-from-browser")
    args = parser.parse_args()

    url = args.url.strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        print("❌ الرابط غير صالح — يجب أن يبدأ بـ http:// أو https://", file=sys.stderr)
        sys.exit(1)

    dest_mp4 = os.path.abspath(args.dest_mp4)
    dest_dir = os.path.dirname(dest_mp4)
    work_dir = os.path.join(dest_dir, "work")
    os.makedirs(dest_dir, exist_ok=True)
    os.makedirs(work_dir, exist_ok=True)
    clean_temp_files(work_dir)

    try:
        try:
            tmp_file, title = download_with_ytdlp(
                url,
                work_dir,
                cookies_file=args.cookies,
                cookies_browser=(args.cookies_browser or "").strip().lower() or None,
            )
        except Exception as err:
            err_msg = str(err)
            if "Unsupported URL" in err_msg or "No video formats" in err_msg:
                tmp_file, title = download_direct_http(url, os.path.join(work_dir, "dl_temp"))
            else:
                raise

        ensure_mp4(tmp_file, dest_mp4)
    except Exception as exc:
        clean_temp_files(work_dir)
        err_text = str(exc)
        low_err = err_text.lower()
        if "confirm you" in low_err and "not a bot" in low_err:
            print(
                "⚠️ يوتيوب يطلب تسجيل الدخول للتحقق من الهوية (حماية رسمية ضد البوتات).\n"
                "💡 الحل الدائم من تبويب «🎨 الهوية ← 5. مصادقة روابط يوتيوب»:\n"
                "   1) اختر متصفح Firefox (لو مسجّل دخولك فيه على يوتيوب — يعمل تلقائياً بدون إضافات)، أو\n"
                "   2) ارفع ملف cookies.txt مرة واحدة من حسابك على يوتيوب.",
                file=sys.stderr,
            )
        elif "dpapi" in low_err or "could not copy chrome cookie" in low_err or "permission denied" in low_err:
            print(
                "⚠️ المتصفح المختار (Chrome/Edge) يقفل قاعدة الكوكيز على ويندوز أثناء تشغيله.\n"
                "💡 الحل: اختر متصفح Firefox من تبويب «الهوية» أو ارفع ملف cookies.txt (يعمل دائماً حتى والمتصفح مفتوح).",
                file=sys.stderr,
            )
        elif "tiktok" in low_err and ("unexpected response from webpage request" in low_err or "impersonat" in low_err):
            print(
                "⚠️ تيك توك حجب التحميل التلقائي للرابط بحماية ضد البوتات (Anti-Bot Challenge).\n"
                "💡 الحل الأسرع والمضمون: احفظ الفيديو على جهازك ثم اسحبه وأفلته مباشرة في استوديو أفستا.",
                file=sys.stderr,
            )
        else:
            print(f"❌ فشل تحميل الفيديو من الرابط: {err_text}", file=sys.stderr)
        sys.exit(1)
    finally:
        clean_temp_files(work_dir)

    if not os.path.exists(dest_mp4) or os.path.getsize(dest_mp4) <= 1024:
        print("❌ الملف المحمّل فارغ أو غير صالح.", file=sys.stderr)
        sys.exit(1)

    size = os.path.getsize(dest_mp4)
    emit_dl(100, "✅ اكتمل تحميل الفيديو بنجاح!")
    result = {"ok": True, "title": title, "size": size, "path": dest_mp4}
    print(f"@RESULT {json.dumps(result, ensure_ascii=False)}", flush=True)


if __name__ == "__main__":
    main()

