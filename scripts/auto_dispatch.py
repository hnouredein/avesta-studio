"""Auto mode: pop the next link from studio/queue.json and start produce.yml with studio/auto.json defaults."""
import json, os, sys, urllib.request

repo = os.environ["GITHUB_REPOSITORY"]; tok = os.environ["GH_TOKEN"]
def api(method, path, body=None):
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req) as r:
        t = r.read(); return json.loads(t) if t else {}

cfg = json.load(open("studio/auto.json")); q = json.load(open("studio/queue.json"))
if not cfg.get("enabled"): print("auto mode off"); sys.exit(0)
if not q: print("queue empty"); sys.exit(0)
busy = 0
for st in ("in_progress", "queued"):
    busy += api("GET", f"/actions/workflows/produce.yml/runs?status={st}&per_page=5").get("total_count", 0)
if busy: print("a production run is active, waiting"); sys.exit(0)
item = q[0]
url = item["url"] if isinstance(item, dict) else item
inputs = {"source_url": url, "title": (item.get("title", "") if isinstance(item, dict) else ""),
          "hook_title": (item.get("hook", "") if isinstance(item, dict) else ""),
          "language": cfg.get("language", "ar"), "whisper_model": cfg.get("whisper_model", "small"),
          "delivery": cfg.get("delivery", "both")}
if cfg.get("settings"): inputs["settings_json"] = json.dumps(cfg["settings"], ensure_ascii=False)
api("POST", "/actions/workflows/produce.yml/dispatches", {"ref": "main", "inputs": inputs})
json.dump(q[1:], open("studio/queue.json", "w"), ensure_ascii=False, indent=1)
print("dispatched", url)
