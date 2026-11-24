# البرومبت 2 — المونتاج الاحترافي الشامل (تستخدمه مع كل فيديو جديد)

> قبل ما تبعته:
> 1. اعمل فولدر جديد جوه `videos/` (مثلاً `videos/01-first-video/`) وحط فيه فيديوك باسم `input.mp4`.
> 2. (اختياري) حط صور أو لقطات توضيحية جوه `videos/01-first-video/broll/`.
> 3. غيّر اسم الفولدر والستايل في أول سطرين من البرومبت لو حابب.

```text
Use the hyperframes skill. Read `brand.md` completely and follow every rule in it (colors, Google Fonts, style mode, captions, RTL rules, audio mastering, color grading, safe zones, glossary, and CTA). Talk to me in natural Egyptian Arabic.

Project folder: videos/01-first-video
Style mode: (use default from brand.md — or override: fast_hook / educational / storytelling)

Follow this professional 100% free local pipeline step by step:

Step 1 — Audio Mastering & Color Grading (Non-destructive):
- NEVER modify or delete `input.mp4`. Save working files in a `work/` subfolder inside the project folder.
- Run `python scripts/master_audio.py <project>/input.mp4 <project>/work/mastered.mp4 --denoise light --lufs -14` to clean room noise, balance vocals, and normalize to -14 LUFS.
- Run `python scripts/color_grade.py <project>/work/mastered.mp4 <project>/work/graded.mp4 --preset <preset_from_brand.md> --vertical` (or `--lut` if a LUT is set in `brand.md`) so the footage is crisp 1080x1920 (9:16).

Step 2 — Word-Level Transcription + Arabic Review Gate:
- First check `npx hyperframes transcribe --help` to confirm syntax.
- Transcribe `<project>/work/graded.mp4` with word-level timestamps using the `small` model (or `medium` if Arabic accuracy is low) with the language from `brand.md`.
- Run `python scripts/clean_transcript.py <transcript.json> --brand brand.md --out <project>/work/cleaned.json` to apply my custom Arabic/English glossary, isolate English words for clean RTL rendering, chunk captions into 3–4 words max, and detect silences > 0.4s (with 0.1s safety padding).
- STOP and show me:
  1. The full cleaned Arabic transcript so I can correct any misheard word/name.
  2. The proposed list of cuts (silences, stutters, repeated fillers) before cutting anything.
- Wait for my approval or edits before proceeding.

Step 3 — Build the Pro Vertical Video (1080x1920, 9:16) with HyperFrames:
After I approve the transcript & cuts, build the video with:
- Tight jump cuts per the approved list (keeping ~0.1s padding so no word gets clipped).
- **Hook (0–3s):** A punchy big Hook title in the first 3 seconds (derived from the strongest line in the speech) with smooth animated entrance.
- **Pro RTL Captions:** Synced word-level/chunk captions (max 3–4 words per line), `dir="rtl"`, English words wrapped in `<span dir="ltr">`, loaded via local `@font-face` from `assets/fonts/Cairo-Variable.ttf` and `assets/fonts/Montserrat-Variable.ttf` (offline, zero network fetches per HyperFrames contract), with 1–2 power words per line highlighted in my brand's Accent color.
- **Visual Pattern Interrupts (every 5–8 seconds):**
  - Subtle animated zooms (`1.04x`–`1.08x`) on key sentences.
  - Clean HTML/SVG motion-graphic callouts (e.g., numbered badges, stat cards, checkmarks, comparison pills) matching `brand.md` whenever I mention a number, list, tip, or key term.
  - If `<project>/broll/` contains any images/clips, weave them in cleanly as timed picture-in-picture or full-frame overlays at the matching moments in my speech.
- **CTA (Last 3s):** Animated Call-to-Action card with my brand logo (if `assets/logo/logo.png` exists) and CTA text from `brand.md`.
- **Strict Safe Zones:** Keep ALL text, cards, and logos at least `380px` from bottom, `150px` from top, and `108px` from left/right.

Step 4 — Background Music (Auto-Ducking) + SFX Mix:
- Create `<project>/work/sfx_cues.json` placing subtle SFX from `assets/sfx/` (`whoosh.wav` on Hook/scene transitions, `pop.wav` on key callouts, `chime.wav` on key tips, `riser.wav` 0.7s before CTA).
- If any audio file exists in `assets/music/`, mix it automatically with sidechain Auto-Ducking (`-22dB` to `-25dB` per `brand.md`) using `python scripts/mix_audio.py` on the rendered video. If `assets/music/` is empty, mix only the SFX cues.

Step 5 — Quality Gate, Preview, Final Render & Publishing Package:
- Run `npx hyperframes check --json` and fix any layout/contrast/lint errors, then run `npx hyperframes snapshot` to visually verify Arabic RTL rendering and safe zones.
- Show me a preview first (`npx hyperframes preview`) and ask if I want any tweaks.
- After I approve:
  1. Save the final mastered & mixed video as `<project>/output.mp4` (never overwrite `input.mp4`).
  2. Render a high-impact thumbnail/cover image as `<project>/cover.png` (`1080x1920`, keeping the headline inside the center `1080x1350` 4:5 Instagram Grid safe zone).
  3. Generate `<project>/post.txt` containing:
     - 3 strong Hook/title variations in Egyptian Arabic
     - Ready-to-paste Instagram/TikTok/Shorts caption
     - 8–12 targeted hashtags
- Tell me in Egyptian Arabic when everything is ready with clickable links to `output.mp4`, `cover.png`, and `post.txt`.
```
