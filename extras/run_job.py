#!/usr/bin/env python3
"""run_job.py - Feed corrected captions into an Avesta job and re-render (stages 5-6 only).

Usage:
  python3 ~/avesta/run_job.py videos/<job> [--corrections corrections.json]

corrections.json: [{"id": <caption id int>, "text": "<corrected Arabic text>"}, ...]
Only captions whose id appears are changed; timings and chunking stay untouched.
Without --corrections it just re-renders from the existing timeline_data.json.
"""
import json
import os
import subprocess
import sys

STUDIO = os.path.expanduser("~/avesta/Avesta-Studio")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    job = sys.argv[1]
    corr_file = None
    if "--corrections" in sys.argv:
        i = sys.argv.index("--corrections")
        corr_file = sys.argv[i + 1]

    job_dir = job if os.path.isabs(job) else os.path.join(STUDIO, job)
    timeline_path = os.path.join(job_dir, "work", "timeline_data.json")
    if not os.path.exists(timeline_path):
        print(f"no timeline at {timeline_path} - run --mode full first")
        return 1

    with open(timeline_path, "r", encoding="utf-8-sig") as f:
        timeline = json.load(f)

    if corr_file:
        with open(corr_file, "r", encoding="utf-8-sig") as f:
            corrections = json.load(f)
        by_id = {int(c["id"]): str(c["text"]) for c in corrections}
        changed = 0
        for cap in timeline.get("captions") or []:
            cid = int(cap.get("id", -1))
            if cid in by_id:
                cap["text"] = by_id[cid]
                # rebuild word-level text so word-by-word highlighting stays consistent
                words = cap.get("words") or []
                if words:
                    tokens = by_id[cid].split()
                    if len(tokens) == len(words):
                        for w, tok in zip(words, tokens):
                            w["word"] = tok
                cap["en_text"] = ""
                changed += 1
        print(f"applied {changed}/{len(by_id)} corrections")
        with open(timeline_path, "w", encoding="utf-8") as f:
            json.dump(timeline, f, ensure_ascii=False, indent=2)

    res = subprocess.run(
        [sys.executable, os.path.join(STUDIO, "scripts", "auto_edit.py"), job, "--mode", "rerender"],
        cwd=STUDIO,
    )
    return res.returncode


if __name__ == "__main__":
    sys.exit(main())
