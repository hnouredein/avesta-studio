# Avesta Studio Pipeline — Portability Guide (GitHub Actions / headless server)

## What a run is

One job = one folder `videos/<job_id>/` containing:

- `input.mp4` — the source video (vertical 1080x1920 works best; pipeline can crop).
- `settings.json` — per-job settings (see example below). Anything omitted falls back to `studio/brand-config.json` (brand identity "غناوي هلنا" is the default profile there).

Run:

```bash
python3 scripts/auto_edit.py videos/<job_id> --mode full
```

Outputs land in the same folder: `output.mp4` (final), `cover.png`, `post.txt`.
Progress lines go to stdout as `@STAGE n/6 ...` markers.
`--mode rerender` re-runs only stages 5-6 from `work/timeline_data.json` — that is how corrected captions are applied without re-transcribing (see `extras/run_job.py`).

Stages: 1 audio master (ffmpeg/pedalboard) → 2 color grade + 9:16 → 3 Whisper transcription → 4 silence cut + transcript clean → 5 HyperFrames render (headless Chrome frame capture + encode) → 6 music/ducking mix + cover + post.

## settings.json example

```json
{
  "title": "عنوان الفيديو",
  "hookTitle": "هوك قصير",
  "language": "en",
  "whisperEnabled": true,
  "whisperModel": "small",
  "autoSmartCrop": false,
  "verticalCrop": false,
  "teaserHookEnabled": false,
  "bilingualCaptions": true,
  "overlays": [ { "mode": "delogo", "x": 0, "y": 1, "w": 100, "h": 9, "start": 0, "end": 0 } ]
}
```

- `language`: spoken language of the source ("en" or "ar"). With `bilingualCaptions: true` the main karaoke caption is Arabic and the original language renders as a small pill under it.
- `overlays` delogo boxes mask source branding; x/y/w/h are percent of frame.
- `whisperModel`: "small" (fast, loops badly on noisy speech) or "medium" (better, needs the model pre-seeded — see below). Our loop transcribes noisy sources with a quantized medium and overwrites `work/timeline_data.json` captions, then `--mode rerender`.

## Dependencies

System (Ubuntu runner):
`sudo apt-get install -y ffmpeg python3 python3-pip fonts-noto fonts-noto-extra` (Noto fonts are REQUIRED for correct Arabic caption shaping in headless Chrome), Node.js >= 22.

Python: `pip install -r requirements.txt` (numpy, edge-tts, pedalboard, yt-dlp). For TikTok sourcing pin `curl_cffi==0.13.0` (0.17 is rejected by yt-dlp's TikTok extractor) and install deno (`~/.deno/bin` on PATH) — yt-dlp needs it for TikTok signature solving.

HyperFrames: the pipeline calls a cached npm `hyperframes` package (>= 0.9.68) from `~/.npm/_npx`, or falls back to the bundled `.agents/skills/hyperframes/scripts/plugin-cli.mjs` (included in this zip). On a fresh runner: `npx -y hyperframes@latest --help` once warms the cache.

## What does NOT move with this zip (re-fetch on the runner)

Everything under `~/.cache/hyperframes/` (about 3.6 GB here):

- `whisper/whisper.cpp/` — whisper.cpp build (whisper-cli + libwhisper). Re-fetch: build from github.com/ggerganov/whisper.cpp or copy release binaries; place at that exact path.
- `whisper/models/ggml-small.bin` (~460 MB) and `ggml-medium.bin` — re-fetch from huggingface.co/ggerganov/whisper.cpp (`ggml-small.bin`, `ggml-medium.bin`). NOTE: our `ggml-medium.bin` is a q5_0 quantization (539 MB) renamed to that filename, because full medium OOMs on small boxes; re-quantize with `whisper-quantize` if you want the same footprint.
- `chrome/chrome-headless-shell/` (~283 MB) — downloaded automatically by HyperFrames on first render; no action needed if the runner has network.
- There is no browser profile/cookies to move — rendering uses profile-less chrome-headless-shell.

Also outside the zip: `~/.npm/_npx` hyperframes cache (warm with npx, above).

## Resource needs (measured on our current 2-core / 1.9 GB box)

- ~90 min for an 80 s video end-to-end (stage 2 ~40 min, stage 5 ~45 min). 4 cores cuts this roughly in half.
- RAM: 4 GB comfortable; 2 GB works only with the q5 medium model and no other load.
- Disk: ~15 GB working set (repo ~10 MB + models 1-2 GB + chrome ~300 MB + per-job work dir 1-3 GB). Prune `videos/<job>/work/` after upload.
- No GPU required; everything is CPU.

## Drive upload (not part of the pipeline)

The pipeline never uploads; our production loop uploads `output.mp4` (re-encoded under 25 MB when needed) to a dated subfolder of the Drive library root via Instinct's Drive tool. On GitHub Actions add an upload step: rclone with a Google service account JSON or OAuth refresh token, and the library folder ID. Secrets needed: `GDRIVE_SA_JSON` (or `RCLONE_CONFIG`) and `DRIVE_FOLDER_ID`. Uploads must stay private — no sharing links.

## Sourcing notes

- YouTube blocks datacenter IPs at login level (all clients fail). TikTok works with the pinned curl_cffi + deno above.
- Verify a candidate has real speech before rendering: transcribe its audio with whisper-cli medium-q5; `[موسيقى]`/`[Music]`-only output means music montage — skip.
