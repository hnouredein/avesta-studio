"""
Quick environment health check for the Free Pro AI Video Editing Studio.
Prints a clean status table of all required tools and workspace assets.
"""

import os
import platform
import shutil
import subprocess
import sys


def get_cmd_version(cmd: list[str]) -> str | None:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace")
        if res.returncode == 0:
            line = (res.stdout or res.stderr).strip().splitlines()
            return line[0].strip() if line else "OK"
    except Exception:
        pass
    return None


def find_chrome() -> str | None:
    candidates = [
        shutil.which("chrome"),
        shutil.which("google-chrome"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(f"OS: {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"Workspace: {root}\n")

    node_ver = get_cmd_version(["node", "-v"])
    node_ok = False
    if node_ver and node_ver.startswith("v"):
        try:
            major = int(node_ver.lstrip("v").split(".")[0])
            node_ok = major >= 22
        except ValueError:
            pass

    npm_ver = get_cmd_version(["npm.cmd" if os.name == "nt" else "npm", "-v"])
    ffmpeg_ver = get_cmd_version(["ffmpeg", "-version"])
    git_ver = get_cmd_version(["git", "--version"])
    chrome_path = find_chrome()
    whisper_path = os.environ.get("HYPERFRAMES_WHISPER_PATH") or shutil.which("whisper-cli")
    whisper_ok = bool(whisper_path and os.path.exists(whisper_path))

    rows = [
        ("Node.js (>=22 LTS)", "OK" if node_ok else ("OUTDATED" if node_ver else "MISSING"), node_ver or "-"),
        ("npm / npx", "OK" if npm_ver else "MISSING", npm_ver or "-"),
        ("FFmpeg", "OK" if ffmpeg_ver else "MISSING", (ffmpeg_ver[:45] + "...") if ffmpeg_ver and len(ffmpeg_ver) > 48 else (ffmpeg_ver or "-")),
        ("Whisper (Speech->Text)", "OK" if whisper_ok else "MISSING", whisper_path or "-"),
        ("Git", "OK" if git_ver else "MISSING", git_ver or "-"),
        ("Google Chrome", "OK" if chrome_path else "MISSING", chrome_path or "-"),
        ("Python", "OK", platform.python_version()),
        ("brand.md", "OK" if os.path.exists(os.path.join(root, "brand.md")) else "MISSING", "brand.md"),
        ("Offline Fonts", "OK" if os.path.exists(os.path.join(root, "assets", "fonts", "Cairo-Variable.ttf")) else "MISSING", "Cairo + Montserrat"),
        ("SFX Library", "OK" if os.path.exists(os.path.join(root, "assets", "sfx", "whoosh.wav")) else "MISSING", "assets/sfx/ (5 files)"),
    ]

    print(f"{'Tool / Component':<24} | {'Status':<10} | Details")
    print("-" * 80)
    for name, status, detail in rows:
        print(f"{name:<24} | {status:<10} | {detail}")


if __name__ == "__main__":
    main()

