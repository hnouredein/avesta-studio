"""Merge app-provided options into the job: settings overrides + extra assets.

env: JOB (project dir), SETTINGS_JSON (object merged over settings.json),
     ASSETS_JSON (list of {kind, url, name}); kinds: music, lut, sfx, broll.
"""
import json
import os
import re
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOB = os.environ["JOB"]
UA = {"User-Agent": "Mozilla/5.0"}
DEST = {
    "music": os.path.join(ROOT, "assets", "music"),
    "lut": os.path.join(ROOT, "assets", "luts"),
    "sfx": os.path.join(ROOT, "assets", "sfx"),
    "broll": os.path.join(JOB, "broll"),
}


def safe(name):
    name = os.path.basename(name or "file")
    return re.sub(r"[^\w.\-\u0600-\u06FF ]", "_", name)[:80] or "file"


def load(env):
    raw = (os.environ.get(env) or "").strip()
    return json.loads(raw) if raw else None


def main():
    path = os.path.join(JOB, "settings.json")
    with open(path, encoding="utf-8") as f:
        s = json.load(f)

    extra = load("SETTINGS_JSON") or {}
    if not isinstance(extra, dict):
        raise SystemExit("SETTINGS_JSON must be an object")
    s.update(extra)

    for a in load("ASSETS_JSON") or []:
        kind = a.get("kind")
        if kind not in DEST:
            print("skip unknown asset kind", kind)
            continue
        os.makedirs(DEST[kind], exist_ok=True)
        name = safe(a.get("name") or a["url"].split("/")[-1])
        out = os.path.join(DEST[kind], name)
        req = urllib.request.Request(a["url"], headers=UA)
        with urllib.request.urlopen(req, timeout=120) as r, open(out, "wb") as w:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                w.write(chunk)
        print(f"asset {kind}: {name} ({os.path.getsize(out)} bytes)")
        if kind == "music":
            s["musicFile"] = name
        elif kind == "lut":
            s["lutFile"] = name
        elif kind == "sfx":
            s.setdefault("customSfx", []).append({
                "file": name, "time": float(a.get("time", 0)), "volume_db": float(a.get("volume_db", -10)),
            })

    if s.get("musicFile") == "none":
        s["musicFile"] = "auto"
        s["musicDb"] = -99

    with open(path, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
    print(json.dumps(s, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
