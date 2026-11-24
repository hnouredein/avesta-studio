import http from "node:http";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, execFile, execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import crypto from "node:crypto";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, "..");
const PUBLIC_DIR = path.join(__dirname, "public");
const BRAND_JSON_PATH = path.join(__dirname, "brand-config.json");
const YT_COOKIES_PATH = path.join(__dirname, "youtube-cookies.txt");
const BRAND_MD_PATH = path.join(ROOT, "brand.md");
const VIDEOS_DIR = path.join(ROOT, "videos");
const ASSETS_DIR = path.join(ROOT, "assets");
const PROMPTS_DIR = path.join(ROOT, "prompts");

const PORT = Number(process.env.STUDIO_PORT || 3456);
process.env.PYTHONUTF8 = "1";
process.env.PYTHONIOENCODING = "utf-8";

function hydrateWindowsEnv() {
  if (process.platform !== "win32") return;
  try {
    const out = execFileSync(
      "powershell.exe",
      [
        "-NoProfile",
        "-Command",
        "$m=[Environment]::GetEnvironmentVariable('Path','Machine');$u=[Environment]::GetEnvironmentVariable('Path','User');$w=[Environment]::GetEnvironmentVariable('HYPERFRAMES_WHISPER_PATH','User');Write-Output \"PATH=$m;$u\";Write-Output \"WHISPER=$w\"",
      ],
      { encoding: "utf8", timeout: 5000 }
    );
    for (const line of out.split(/\r?\n/)) {
      if (line.startsWith("PATH=") && line.length > 5) {
        process.env.PATH = line.slice(5);
      } else if (line.startsWith("WHISPER=") && line.length > 8) {
        process.env.HYPERFRAMES_WHISPER_PATH = line.slice(8).trim();
      }
    }
  } catch {
    // Fallback to inherited env
  }
}

hydrateWindowsEnv();

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".ttf": "font/ttf",
  ".woff2": "font/woff2",
  ".mp4": "video/mp4",
  ".mov": "video/quicktime",
  ".webm": "video/webm",
  ".wav": "audio/wav",
  ".mp3": "audio/mpeg",
  ".m4a": "audio/mp4",
  ".txt": "text/plain; charset=utf-8",
  ".md": "text/markdown; charset=utf-8",
};

const jobs = new Map();

function safeSlug(name) {
  // Always generate a Windows/FFmpeg/Whisper-safe ASCII folder slug (no trailing dots, no diacritics/unicode path bugs).
  // The original Arabic display name is preserved inside settings.json -> title!
  const cleaned = String(name || "")
    .trim()
    .replace(/\.[^/.]+$/, "")
    .replace(/[^a-zA-Z0-9_-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^[-_.]+|[-_.]+$/g, "")
    .slice(0, 40)
    .toLowerCase();
  return cleaned || `video-${Date.now().toString().slice(-5)}`;
}

function safeFilename(name) {
  const base = path.basename(String(name || "file.bin")).replace(/[\\/:*?"<>|]/g, "_").replace(/[. ]+$/, "");
  return base || "file.bin";
}

function isInside(parent, child) {
  const rel = path.relative(path.resolve(parent), path.resolve(child));
  return Boolean(rel && !rel.startsWith("..") && !path.isAbsolute(rel));
}

function sendJson(res, status, data) {
  const body = JSON.stringify(data);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
  res.end(body);
}

function readJsonBody(req, maxBytes = 4 * 1024 * 1024) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let total = 0;
    req.on("data", (chunk) => {
      total += chunk.length;
      if (total > maxBytes) {
        reject(new Error("Payload too large"));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => {
      try {
        const text = Buffer.concat(chunks).toString("utf8");
        resolve(text ? JSON.parse(text) : {});
      } catch (err) {
        reject(err);
      }
    });
    req.on("error", reject);
  });
}

function saveRawUpload(req, destPath) {
  return new Promise((resolve, reject) => {
    fs.mkdirSync(path.dirname(destPath), { recursive: true });
    const ws = fs.createWriteStream(destPath);
    let size = 0;
    req.on("data", (c) => {
      size += c.length;
    });
    req.pipe(ws);
    ws.on("finish", () => resolve(size));
    ws.on("error", reject);
    req.on("error", reject);
  });
}

function serveFileWithRange(req, res, filePath) {
  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
    res.writeHead(404);
    res.end("Not found");
    return;
  }
  const stat = fs.statSync(filePath);
  const ext = path.extname(filePath).toLowerCase();
  const mime = MIME_TYPES[ext] || "application/octet-stream";
  const range = req.headers.range;

  if (range) {
    const parts = range.replace(/bytes=/, "").split("-");
    const start = parseInt(parts[0], 10);
    const end = parts[1] ? parseInt(parts[1], 10) : stat.size - 1;
    if (Number.isNaN(start) || start >= stat.size || end >= stat.size) {
      res.writeHead(416, { "Content-Range": `bytes */${stat.size}` });
      res.end();
      return;
    }
    const chunkSize = end - start + 1;
    res.writeHead(206, {
      "Content-Range": `bytes ${start}-${end}/${stat.size}`,
      "Accept-Ranges": "bytes",
      "Content-Length": chunkSize,
      "Content-Type": mime,
    });
    fs.createReadStream(filePath, { start, end }).pipe(res);
  } else {
    res.writeHead(200, {
      "Content-Length": stat.size,
      "Content-Type": mime,
      "Accept-Ranges": "bytes",
    });
    fs.createReadStream(filePath).pipe(res);
  }
}

function isGenericVideoName(raw) {
  const s = String(raw || "").trim();
  if (!s || s.length < 3) return true;
  const low = s.toLowerCase();
  if (["فيديو جديد", "فيديو من رابط...", "فيديو من رابط", "video", "output", "input", "clip", "reel", "short"].includes(low)) {
    return true;
  }
  if (/^(\d{2}-|video[-_ ]?|new-video|my-video|url-video|youtube-video|tiktok-video|facebook-video|instagram-video|vid[-_]|img[-_]|pxl[-_]|dji[-_]|screen|whatsapp|download|snaptik|ssstik|saveinsta|savett|tikmate|fbdown|fdown|aq[a-z0-9]{6,}|snapinsta)/i.test(s)) {
    return true;
  }
  const letters = s.replace(/[^A-Za-z\u0600-\u06FF]/g, "");
  if (letters.length < 3) return true;
  if (/^[A-Za-z0-9_-]{8,}$/.test(s) && (s.match(/\d/g) || []).length >= 4) return true;
  return false;
}

function sanitizeWindowsFilename(name, maxLen = 62) {
  let clean = String(name || "")
    .replace(/[#_]+/g, " ")
    .replace(/[<>:"/\\|?*\r\n\t]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/^[ ._-]+|[ ._-]+$/g, "");
  if (clean.length > maxLen) {
    const cut = clean.slice(0, maxLen).replace(/\s+\S*$/, "").replace(/[ ._-]+$/g, "");
    clean = cut.length >= 12 ? cut : clean.slice(0, maxLen).replace(/[ ._-]+$/g, "");
  }
  return clean;
}

function buildRealisticExportName(settings, timeline, brand) {
  const candidates = [];
  if (!isGenericVideoName(settings?.hookTitle)) candidates.push(settings.hookTitle);
  if (!isGenericVideoName(settings?.title)) candidates.push(settings.title);
  if (!isGenericVideoName(timeline?.auto_hook)) candidates.push(timeline.auto_hook);
  if (timeline?.full_text) {
    const words = String(timeline.full_text)
      .split(/\s+/)
      .map((w) => w.replace(/^[.,،!؟?"'()[\]]+|[.,،!؟?"'()[\]]+$/g, ""))
      .filter(Boolean);
    if (words.length >= 2) {
      const phrase = words.slice(0, 7).join(" ");
      if (!isGenericVideoName(phrase)) candidates.push(phrase);
    }
  }
  for (const ov of settings?.overlays || []) {
    if (ov && ov.mode === "replace" && ov.text) {
      const txt = String(ov.text).replace(/\s+/g, " ").trim();
      if (!isGenericVideoName(txt)) {
        candidates.push(txt);
        break;
      }
    }
  }
  for (const c of candidates) {
    const safe = sanitizeWindowsFilename(c);
    if (safe && !isGenericVideoName(safe)) return safe;
  }
  const acct = sanitizeWindowsFilename(brand?.accountName || "غناوي هلنا", 28) || "غناوي هلنا";
  const now = new Date();
  const stamp = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}_${String(now.getHours()).padStart(2, "0")}-${String(now.getMinutes()).padStart(2, "0")}`;
  return `${acct} - مقطع ${stamp}`;
}

function readBrandConfig() {
  if (fs.existsSync(BRAND_JSON_PATH)) {
    return JSON.parse(fs.readFileSync(BRAND_JSON_PATH, "utf8"));
  }
  return {};
}

function resolveBrandProfile(brand, profileId) {
  const chosenId = (profileId || brand?.defaultProfileId || "ghinawi_halna").trim();
  const prof = (brand?.profiles || []).find((p) => p && p.id === chosenId);
  if (!prof) return { ...(brand || {}), id: chosenId };
  return {
    ...(brand || {}),
    ...prof,
    id: chosenId,
    colors: { ...(brand?.colors || {}), ...(prof.colors || {}) },
  };
}

function hexToRgba(hex, alpha = 0.78) {
  const clean = String(hex || "#0C0C10").replace("#", "");
  const r = parseInt(clean.slice(0, 2), 16) || 12;
  const g = parseInt(clean.slice(2, 4), 16) || 12;
  const b = parseInt(clean.slice(4, 6), 16) || 16;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function syncBrandMarkdown(cfg) {
  const surfaceRgba = hexToRgba(cfg.colors?.surface, cfg.colors?.surfaceOpacity ?? 0.78);
  const glossaryLines = (cfg.glossary || [])
    .filter((g) => g.wrong && g.right)
    .map((g) => `- ${g.wrong} -> ${g.right}`)
    .join("\n");

  const md = `# الهوية البصرية ونظام المونتاج — Brand Identity (Pro)

> تم التحديث تلقائياً من واجهة الاستوديو (\`studio/brand-config.json\`).

---

## 1. البيانات الأساسية (Identity)
- **اسم الحساب / البراند:** ${cfg.accountName || ""}
- **المجال / المحتوى:** ${cfg.niche || ""}
- **المنصة الأساسية:** ${cfg.platform || "Reels / TikTok / YouTube Shorts"}
- **لغة الكلام في الفيديوهات:** ${cfg.dialectLabel || "Egyptian Arabic"} (\`${cfg.language || "ar"}\`)
- **اللوجو:** ${cfg.logoFile ? `\`assets/logo/${cfg.logoFile}\`` : "(غير محدد)"}
- **جملة الخاتمة (CTA):** "${cfg.cta || ""}"

---

## 2. الألوان والخطوط (Colors & Typography)
- **اللون الأساسي (Primary):** \`${cfg.colors?.primary || "#FFFFFF"}\`
- **اللون المميّز (Accent):** \`${cfg.colors?.accent || "#FFD60A"}\`
- **لون التمييز الثانوي (Secondary):** \`${cfg.colors?.secondary || "#FF3B30"}\`
- **لون خلفية الكروت والترجمة (Surface):** \`${surfaceRgba}\`
- **الخط العربي (Offline):** \`${cfg.fonts?.arabic || "Cairo"}\` (\`assets/fonts/Cairo-Variable.ttf\`)
- **الخط الإنجليزي (Offline):** \`${cfg.fonts?.english || "Montserrat"}\` (\`assets/fonts/Montserrat-Variable.ttf\`)

---

## 3. الإعدادات الافتراضية
- **الستايل:** \`${cfg.defaults?.styleMode || "fast_hook"}\`
- **الترجمة:** \`${cfg.defaults?.captionStyle || "chunk_highlight"}\` (حد أقصى \`${cfg.defaults?.maxWords || 4}\` كلمات)
- **الصوت:** \`denoise=${cfg.defaults?.denoise || "light"}\` · \`lufs=${cfg.defaults?.lufs ?? -14}\`
- **الألوان:** \`${cfg.defaults?.colorPreset || "warm_creator"}\`
- **Whisper:** \`${cfg.defaults?.whisperModel || "small"}\` · قصّ السكوت > \`${cfg.defaults?.minSilence ?? 0.4}s\` (padding \`${cfg.defaults?.cutPad ?? 0.1}s\`)

---

## 4. المساحات الآمنة (Safe Zones — 1080x1920)
- أعلى: \`${cfg.safeZones?.top ?? 150}px\` · أسفل: \`${cfg.safeZones?.bottom ?? 380}px\` · جوانب: \`${cfg.safeZones?.sides ?? 108}px\`

---

## 5. قاموس التصحيح التلقائي (Custom Glossary)
${glossaryLines || "- أنتي جرافيتي -> Antigravity"}
`;
  fs.writeFileSync(BRAND_MD_PATH, md, "utf8");
}

function defaultProjectSettings(brand, title = "", profileId = "") {
  const chosenProfileId = (profileId || brand.defaultProfileId || "ghinawi_halna").trim();
  const prof = resolveBrandProfile(brand, chosenProfileId);
  return {
    title: title || "",
    brandProfile: chosenProfileId,
    hookTitle: "",
    ctaText: prof.cta || brand.cta || "تابعني ومش هتندم",
    styleMode: brand.defaults?.styleMode || "fast_hook",
    captionStyle: brand.defaults?.captionStyle || "karaoke",
    bilingualCaptions: brand.defaults?.bilingualCaptions !== false,
    maxWords: brand.defaults?.maxWords || 4,
    denoise: brand.defaults?.denoise || "light",
    voicePreset: brand.defaults?.voicePreset || "studio",
    lufs: brand.defaults?.lufs ?? -14,
    colorPreset: brand.defaults?.colorPreset || "warm_creator",
    lutFile: brand.defaults?.lutFile || "",
    verticalCrop: true,
    musicFile: brand.defaults?.musicFile ?? "",
    musicDb: brand.defaults?.musicDb ?? -23,
    autoDuck: brand.defaults?.autoDuck !== false,
    sfxEnabled: brand.defaults?.sfxEnabled !== false,
    sfxDb: brand.defaults?.sfxDb ?? -5,
    whisperEnabled: brand.defaults?.whisperEnabled !== false,
    autoCutSilences: brand.defaults?.autoCutSilences !== false,
    whisperModel: brand.defaults?.whisperModel || "small",
    renderQuality: brand.defaults?.renderQuality || "standard",
    language: brand.language || "ar",
    minSilence: brand.defaults?.minSilence ?? 0.4,
    cutPad: brand.defaults?.cutPad ?? 0.1,
    trimStart: 0,
    trimEnd: 0,
    fitMode: brand.defaults?.fitMode || "cover",
    autoSmartCrop: brand.defaults?.autoSmartCrop !== false,
    cropZoom: 1,
    cropPanX: 0,
    cropPanY: 0,
    cropTop: 0,
    cropBottom: 0,
    showHookCard: brand.defaults?.showHookCard !== false,
    showWatermark: true,
    salawatOutro: Boolean(brand.defaults?.salawatOutro),
    teaserHookEnabled: brand.defaults?.teaserHookEnabled !== false,
    teaserMode: "auto",
    teaserStart: 0,
    teaserDuration: brand.defaults?.teaserDuration ?? 3,
    teaserBadge: brand.defaults?.teaserBadge || "شاهد للنهاية 🔥",
    overlays: [],
    audioSource: "original",
    muteOriginal: false,
    voiceDb: 0,
    originalDb: -10,
    ttsText: "",
    ttsVoice: "salma",
    ttsRate: "+0%",
    customSfx: [],
    accentOverride: "",
    customNotes: "",
    updatedAt: new Date().toISOString(),
  };
}

function nextUniqueProjectSlug(baseName) {
  const existing = fs.existsSync(VIDEOS_DIR)
    ? fs.readdirSync(VIDEOS_DIR).filter((n) => fs.statSync(path.join(VIDEOS_DIR, n)).isDirectory())
    : [];
  const prefix = String(existing.length + 1).padStart(2, "0");
  let slug = safeSlug(baseName);
  if (!/^\d{2}-/.test(slug)) slug = `${prefix}-${slug}`;
  let candidate = slug;
  let counter = 2;
  while (fs.existsSync(path.join(VIDEOS_DIR, candidate))) {
    candidate = `${slug}-${counter++}`;
  }
  return candidate;
}

function probeVideo(filePath) {
  if (!filePath || !fs.existsSync(filePath)) return null;
  try {
    const out = execFileSync(
      "ffprobe",
      [
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height:format=duration,size",
        "-of", "json",
        filePath,
      ],
      { encoding: "utf8", timeout: 4000 }
    );
    const parsed = JSON.parse(out);
    const s = parsed.streams?.[0] || {};
    const f = parsed.format || {};
    return {
      width: s.width || null,
      height: s.height || null,
      duration: f.duration ? Number(Number(f.duration).toFixed(2)) : null,
      sizeBytes: f.size ? Number(f.size) : fs.statSync(filePath).size,
    };
  } catch {
    return { sizeBytes: fs.statSync(filePath).size };
  }
}

function listAssets() {
  const scan = (subdir, exts) => {
    const dir = path.join(ASSETS_DIR, subdir);
    if (!fs.existsSync(dir)) return [];
    return fs
      .readdirSync(dir)
      .filter((f) => {
        const full = path.join(dir, f);
        if (fs.statSync(full).isDirectory()) return false;
        if (f.toLowerCase() === "readme.md") return false;
        return !exts || exts.includes(path.extname(f).toLowerCase());
      })
      .map((f) => ({
        name: f,
        sizeBytes: fs.statSync(path.join(dir, f)).size,
        url: `/media/assets/${subdir}/${encodeURIComponent(f)}`,
      }));
  };
  return {
    music: scan("music", [".mp3", ".wav", ".m4a", ".ogg"]),
    sfx: scan("sfx", [".wav", ".mp3", ".ogg"]),
    logo: scan("logo", [".png", ".svg", ".webp", ".jpg", ".jpeg"]),
    luts: scan("luts", [".cube"]),
    fonts: scan("fonts", [".ttf", ".otf", ".woff2"]),
  };
}

function dirSizeBytes(dirPath) {
  let total = 0;
  try {
    for (const entry of fs.readdirSync(dirPath, { withFileTypes: true })) {
      const full = path.join(dirPath, entry.name);
      if (entry.isDirectory()) total += dirSizeBytes(full);
      else if (entry.isFile()) total += fs.statSync(full).size;
    }
  } catch {}
  return total;
}

function inspectProject(id) {
  const dir = path.join(VIDEOS_DIR, id);
  if (!fs.existsSync(dir) || !fs.statSync(dir).isDirectory()) return null;
  const brand = readBrandConfig();
  const settingsPath = path.join(dir, "settings.json");
  let settings;
  if (fs.existsSync(settingsPath)) {
    settings = { ...defaultProjectSettings(brand, id), ...JSON.parse(fs.readFileSync(settingsPath, "utf8")) };
  } else {
    settings = defaultProjectSettings(brand, id);
  }

  const inputPath = path.join(dir, "input.mp4");
  const testPath = path.join(dir, "test.mp4");
  const cropPreviewPath = path.join(dir, "work", "crop_preview.mp4");
  const masteredPath = path.join(dir, "work", "mastered.mp4");
  const gradedPath = path.join(dir, "work", "graded.mp4");
  const cutPath = path.join(dir, "work", "cut.mp4");
  const outputPath = path.join(dir, "output.mp4");
  const coverPath = path.join(dir, "cover.png");
  const postPath = path.join(dir, "post.txt");
  const timelinePath = path.join(dir, "work", "timeline_data.json");
  const brollDir = path.join(dir, "broll");

  const broll = fs.existsSync(brollDir)
    ? fs
        .readdirSync(brollDir)
        .filter((f) => f.toLowerCase() !== "readme.md" && !fs.statSync(path.join(brollDir, f)).isDirectory())
        .map((f) => ({
          name: f,
          sizeBytes: fs.statSync(path.join(brollDir, f)).size,
          url: `/media/videos/${encodeURIComponent(id)}/broll/${encodeURIComponent(f)}`,
        }))
    : [];

  const hasInput = fs.existsSync(inputPath);
  const hasMastered = fs.existsSync(masteredPath);
  const hasGraded = fs.existsSync(gradedPath);
  const hasCut = fs.existsSync(cutPath);
  const hasOutput = fs.existsSync(outputPath);
  const hasTest = fs.existsSync(testPath);
  const hasCover = fs.existsSync(coverPath);
  const hasPost = fs.existsSync(postPath);
  const hasTimeline = fs.existsSync(timelinePath);

  let status = "empty";
  if (hasOutput || hasTest) status = "done";
  else if (hasCut || hasGraded || hasMastered) status = "prepped";
  else if (hasInput) status = "raw";

  const outputUrl = hasOutput
    ? `/media/videos/${encodeURIComponent(id)}/output.mp4`
    : hasTest
      ? `/media/videos/${encodeURIComponent(id)}/test.mp4`
      : null;

  const previewUrl = outputUrl
    || (hasGraded ? `/media/videos/${encodeURIComponent(id)}/work/graded.mp4` : null)
    || (hasInput ? `/media/videos/${encodeURIComponent(id)}/input.mp4` : null);

  let timeline = null;
  if (hasTimeline) {
    try {
      timeline = JSON.parse(fs.readFileSync(timelinePath, "utf8"));
    } catch {
      timeline = null;
    }
  }

  return {
    id,
    status,
    diskBytes: dirSizeBytes(dir),
    settings,
    files: {
      hasInput,
      hasMastered,
      hasGraded,
      hasCut,
      hasOutput,
      hasTest,
      hasCover,
      hasPost,
      hasTimeline,
      inputUrl: hasInput ? `/media/videos/${encodeURIComponent(id)}/input.mp4` : null,
      cropPreviewUrl: fs.existsSync(cropPreviewPath) ? `/media/videos/${encodeURIComponent(id)}/work/crop_preview.mp4` : null,
      gradedUrl: hasGraded ? `/media/videos/${encodeURIComponent(id)}/work/graded.mp4` : null,
      outputUrl,
      coverUrl: hasCover ? `/media/videos/${encodeURIComponent(id)}/cover.png` : null,
      previewUrl,
    },
    postText: hasPost ? fs.readFileSync(postPath, "utf8") : "",
    timeline,
    probe: probeVideo(hasOutput ? outputPath : hasTest ? testPath : hasGraded ? gradedPath : inputPath),
    broll,
  };
}

function listProjects() {
  if (!fs.existsSync(VIDEOS_DIR)) return [];
  return fs
    .readdirSync(VIDEOS_DIR)
    .filter((name) => fs.statSync(path.join(VIDEOS_DIR, name)).isDirectory())
    .sort()
    .map((id) => inspectProject(id))
    .filter(Boolean);
}

function buildTailoredPrompt(project, brand) {
  const s = project.settings;
  const accent = s.accentOverride || brand.colors?.accent || "#FFD60A";
  return `Use the hyperframes skill. Read \`brand.md\` and \`videos/${project.id}/settings.json\`. Talk to me in natural Egyptian Arabic.

Project folder: videos/${project.id}
Title: ${s.title || project.id}
Style Mode: ${s.styleMode}
Hook: ${s.hookTitle ? `"${s.hookTitle}"` : "(auto)"}
CTA: "${s.ctaText || brand.cta}"
Accent: ${accent}
Extra Notes: ${s.customNotes || "None"}

Edit or refine this video further using HyperFrames (keeping input.mp4 untouched) and update videos/${project.id}/output.mp4, cover.png, and post.txt.`;
}

function getSystemStatus() {
  const checkCmd = (cmd, args) => {
    try {
      const out = execFileSync(cmd, args, { encoding: "utf8", timeout: 4000 });
      return { ok: true, detail: out.trim().split(/\r?\n/)[0] };
    } catch {
      return { ok: false, detail: "غير متوفر" };
    }
  };
  const chromeCandidates = [
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    path.join(process.env.LOCALAPPDATA || "", "Google\\Chrome\\Application\\chrome.exe"),
  ];
  const chromePath = chromeCandidates.find((p) => p && fs.existsSync(p));
  const whisperPath = process.env.HYPERFRAMES_WHISPER_PATH;
  const skillsInstalled = fs.existsSync(path.join(ROOT, ".agents", "skills", "hyperframes", "SKILL.md"));

  return {
    node: { ok: Number(process.versions.node.split(".")[0]) >= 22, detail: `v${process.versions.node}` },
    ffmpeg: checkCmd("ffmpeg", ["-version"]),
    whisper: {
      ok: Boolean(whisperPath && fs.existsSync(whisperPath)),
      detail: whisperPath ? path.basename(whisperPath) : "غير مضبوط",
    },
    chrome: { ok: Boolean(chromePath), detail: chromePath ? "Google Chrome (GPU Ready)" : "غير موجود" },
    hyperframes: { ok: skillsInstalled, detail: skillsInstalled ? "v0.9.70 + 9 Skills" : "غير مثبّت" },
    python: checkCmd("python", ["--version"]),
    ytdlp: checkCmd("python", ["-m", "yt_dlp", "--version"]),
    ytCookies: { ok: fs.existsSync(YT_COOKIES_PATH), detail: fs.existsSync(YT_COOKIES_PATH) ? "مفعّل (cookies.txt)" : "غير مرفوع" },
  };
}

const activeProjectProcs = new Map();

function killProcessTree(proc) {
  if (!proc || !proc.pid) return;
  try {
    if (process.platform === "win32") {
      execFileSync("taskkill", ["/PID", String(proc.pid), "/T", "/F"], { stdio: "ignore", timeout: 5000 });
    } else {
      proc.kill("SIGTERM");
    }
  } catch {}
}

function attachAutoEditProcess(job, projectDir, mode, minPct = 0) {
  const key = path.resolve(projectDir);
  const prev = activeProjectProcs.get(key);
  if (prev && prev.proc && prev.proc.exitCode === null) {
    prev.cancelled = true;
    prev.job.status = "error";
    prev.job.finishedAt = new Date().toISOString();
    prev.job.stageLabel = "⏹️ تم إلغاء الرندر السابق لبدء رندر أحدث لنفس المشروع.";
    killProcessTree(prev.proc);
  }

  const proc = spawn(
    "python",
    ["-u", path.join(ROOT, "scripts", "auto_edit.py"), projectDir, "--mode", mode],
    { cwd: ROOT, env: { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" } }
  );
  const entry = { proc, job, cancelled: false };
  activeProjectProcs.set(key, entry);

  const handleChunk = (chunk) => {
    const text = chunk.toString("utf8");
    for (const rawLine of text.split(/\r?\n/)) {
      const line = rawLine.trimEnd();
      if (!line) continue;
      const m = line.match(/^@STAGE\s+(\d+)\/(\d+)\s+(\d+)\s+(.+)$/);
      if (m) {
        job.stageStep = Number(m[1]);
        job.stageTotal = Number(m[2]);
        job.pct = Math.max(minPct, Number(m[3]));
        job.stageLabel = m[4].trim();
        job.logs.push(`━━━ [${job.stageStep}/${job.stageTotal}] ${job.stageLabel}`);
      } else {
        job.logs.push(line);
        if (job.logs.length > 400) job.logs.shift();
      }
    }
  };

  proc.stdout.on("data", handleChunk);
  proc.stderr.on("data", handleChunk);
  proc.on("close", (code) => {
    if (activeProjectProcs.get(key) === entry) activeProjectProcs.delete(key);
    if (entry.cancelled) return;
    job.finishedAt = new Date().toISOString();
    if (code === 0) {
      job.status = "done";
      job.pct = 100;
      if (!job.stageLabel.includes("✅")) job.stageLabel = "✅ اكتمل المونتاج بنجاح!";
    } else {
      job.status = "error";
      job.stageLabel = `❌ توقّفت العملية بكود خطأ ${code}`;
      job.logs.push(job.stageLabel);
    }
  });
  proc.on("error", (err) => {
    if (activeProjectProcs.get(key) === entry) activeProjectProcs.delete(key);
    if (entry.cancelled) return;
    job.status = "error";
    job.finishedAt = new Date().toISOString();
    job.stageLabel = `❌ خطأ تشغيل: ${err.message}`;
    job.logs.push(job.stageLabel);
  });
}

function startAutoEditJob(projectDir, mode) {
  const jobId = crypto.randomUUID();
  const job = {
    id: jobId,
    status: "running",
    stageStep: 0,
    stageTotal: 6,
    pct: 3,
    stageLabel: "جاري تجهيز المحرك...",
    logs: [],
    startedAt: new Date().toISOString(),
    finishedAt: null,
  };
  jobs.set(jobId, job);
  attachAutoEditProcess(job, projectDir, mode, 0);
  return jobId;
}

function startUrlImportJob(projectId, projectDir, url, autoEdit) {
  const jobId = crypto.randomUUID();
  const destMp4 = path.join(projectDir, "input.mp4");
  const settingsPath = path.join(projectDir, "settings.json");
  const job = {
    id: jobId,
    projectId,
    status: "running",
    stageStep: 0,
    stageTotal: 6,
    pct: 2,
    stageLabel: "⬇️ جاري تحميل الفيديو من الرابط...",
    logs: [`🔗 الرابط: ${url}`],
    startedAt: new Date().toISOString(),
    finishedAt: null,
  };
  jobs.set(jobId, job);

  const dlArgs = ["-u", path.join(ROOT, "scripts", "download_url.py"), url, destMp4];
  const brandCfg = readBrandConfig();
  const ytAuthMode = String(brandCfg?.defaults?.ytAuthMode || "auto");
  if (ytAuthMode === "cookies_file" || (ytAuthMode === "auto" && fs.existsSync(YT_COOKIES_PATH))) {
    if (fs.existsSync(YT_COOKIES_PATH)) {
      dlArgs.push("--cookies", YT_COOKIES_PATH);
    }
  } else if (["firefox", "edge", "chrome", "brave", "opera", "vivaldi"].includes(ytAuthMode)) {
    dlArgs.push("--cookies-browser", ytAuthMode);
  }
  const dlProc = spawn(
    "python",
    dlArgs,
    { cwd: ROOT, env: { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" } }
  );

  const handleDlChunk = (chunk) => {
    const text = chunk.toString("utf8");
    for (const rawLine of text.split(/\r?\n/)) {
      const line = rawLine.trimEnd();
      if (!line) continue;
      const dlMatch = line.match(/^@DL\s+(\d+)\s+(.+)$/);
      if (dlMatch) {
        const rawPct = Number(dlMatch[1]);
        job.pct = autoEdit ? Math.min(14, Math.max(2, Math.round(rawPct * 0.14))) : rawPct;
        job.stageLabel = dlMatch[2].trim();
        job.logs.push(job.stageLabel);
        if (job.logs.length > 400) job.logs.shift();
        continue;
      }
      if (line.startsWith("@RESULT ")) {
        try {
          const info = JSON.parse(line.slice(8));
          if (info.title && fs.existsSync(settingsPath)) {
            const cur = JSON.parse(fs.readFileSync(settingsPath, "utf8"));
            cur.title = info.title;
            cur.updatedAt = new Date().toISOString();
            fs.writeFileSync(settingsPath, JSON.stringify(cur, null, 2), "utf8");
          }
        } catch {}
        continue;
      }
      job.logs.push(line);
      if (job.logs.length > 400) job.logs.shift();
    }
  };

  dlProc.stdout.on("data", handleDlChunk);
  dlProc.stderr.on("data", handleDlChunk);
  dlProc.on("close", (code) => {
    if (code !== 0 || !fs.existsSync(destMp4)) {
      try {
        if (isInside(VIDEOS_DIR, projectDir) && fs.existsSync(projectDir)) {
          fs.rmSync(projectDir, { recursive: true, force: true });
        }
      } catch {}
      job.status = "error";
      job.finishedAt = new Date().toISOString();
      job.stageLabel = "❌ فشل تحميل الفيديو من الرابط — تأكد إن الرابط عام وصالح.";
      job.logs.push(job.stageLabel);
      return;
    }

    if (!autoEdit) {
      job.status = "done";
      job.pct = 100;
      job.finishedAt = new Date().toISOString();
      job.stageLabel = "✅ تم تحميل الفيديو بنجاح وجاهز للمونتاج!";
      job.logs.push(job.stageLabel);
      return;
    }

    job.pct = 15;
    job.stageLabel = "🚀 اكتمل التحميل! جاري بدء المونتاج التلقائي فوراً...";
    job.logs.push("✅ اكتمل التحميل! جاري بدء المونتاج التلقائي فوراً...");
    attachAutoEditProcess(job, projectDir, "full", 15);
  });

  dlProc.on("error", (err) => {
    job.status = "error";
    job.finishedAt = new Date().toISOString();
    job.stageLabel = `❌ خطأ تشغيل المحمّل: ${err.message}`;
    job.logs.push(job.stageLabel);
  });

  return jobId;
}

const server = http.createServer(async (req, res) => {
  try {
    const urlObj = new URL(req.url, `http://localhost:${PORT}`);
    const pathname = decodeURIComponent(urlObj.pathname);

    if (pathname === "/favicon.ico" && req.method === "GET") {
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="16" fill="#FFD60A"/><text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" font-family="Arial,sans-serif" font-weight="900" font-size="36" fill="#080A0F">A</text></svg>`;
      res.writeHead(200, { "Content-Type": "image/svg+xml", "Cache-Control": "public, max-age=86400" });
      res.end(svg);
      return;
    }

    if (pathname === "/api/status" && req.method === "GET") {
      return sendJson(res, 200, getSystemStatus());
    }

    if (pathname === "/api/brand" && req.method === "GET") {
      return sendJson(res, 200, readBrandConfig());
    }

    if (pathname === "/api/brand" && req.method === "POST") {
      const body = await readJsonBody(req);
      const cur = readBrandConfig();
      const editingId = body.editingProfileId;
      delete body.editingProfileId;
      const merged = {
        ...cur,
        ...body,
        defaultProfileId: body.defaultProfileId || cur.defaultProfileId || "ghinawi_halna",
        defaults: { ...(cur.defaults || {}), ...(body.defaults || {}) },
        colors: { ...(cur.colors || {}), ...(body.colors || {}) },
        profiles: Array.isArray(body.profiles) ? body.profiles : cur.profiles || [],
      };
      if (editingId && Array.isArray(merged.profiles)) {
        const idx = merged.profiles.findIndex((p) => p && p.id === editingId);
        if (idx >= 0) {
          merged.profiles[idx] = {
            ...merged.profiles[idx],
            accountName: merged.accountName,
            niche: merged.niche,
            dialectLabel: merged.dialectLabel,
            cta: merged.cta,
            colors: { ...(merged.profiles[idx].colors || {}), ...(merged.colors || {}) },
          };
        }
      }
      fs.writeFileSync(BRAND_JSON_PATH, JSON.stringify(merged, null, 2), "utf8");
      syncBrandMarkdown(merged);
      return sendJson(res, 200, { ok: true, synced: ["studio/brand-config.json", "brand.md"], brand: merged });
    }

    if (pathname === "/api/assets" && req.method === "GET") {
      return sendJson(res, 200, listAssets());
    }

    if (pathname === "/api/cookies/upload" && req.method === "POST") {
      const size = await saveRawUpload(req, YT_COOKIES_PATH);
      return sendJson(res, 200, { ok: true, size });
    }

    if (pathname === "/api/cookies" && req.method === "DELETE") {
      if (fs.existsSync(YT_COOKIES_PATH)) fs.unlinkSync(YT_COOKIES_PATH);
      return sendJson(res, 200, { ok: true });
    }

    if (pathname === "/api/recent-downloads" && req.method === "GET") {
      const brand = readBrandConfig();
      const videoExts = new Set([".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"]);
      const dirsToScan = [path.join(os.homedir(), "Downloads")];
      const extraDir = String(brand?.defaults?.watchFolder || "").trim().replace(/^["']|["']$/g, "");
      if (extraDir && fs.existsSync(extraDir) && !dirsToScan.includes(extraDir)) {
        dirsToScan.push(extraDir);
      }
      const items = [];
      for (const scanDir of dirsToScan) {
        if (!scanDir || !fs.existsSync(scanDir)) continue;
        try {
          for (const fname of fs.readdirSync(scanDir)) {
            const ext = path.extname(fname).toLowerCase();
            if (!videoExts.has(ext)) continue;
            const full = path.join(scanDir, fname);
            try {
              const st = fs.statSync(full);
              if (st.isFile() && st.size > 4096) {
                items.push({
                  name: fname,
                  path: full,
                  sizeBytes: st.size,
                  mtimeMs: st.mtimeMs,
                  folder: path.basename(scanDir),
                });
              }
            } catch {}
          }
        } catch {}
      }
      items.sort((a, b) => b.mtimeMs - a.mtimeMs);
      return sendJson(res, 200, { files: items.slice(0, 8), dirs: dirsToScan });
    }

    if (pathname === "/api/tools/update-ytdlp" && req.method === "POST") {
      try {
        await new Promise((resolve, reject) => {
          execFile(
            "python",
            ["-m", "pip", "install", "-U", "yt-dlp"],
            { cwd: ROOT, encoding: "utf8", timeout: 120000, maxBuffer: 4 * 1024 * 1024 },
            (err, stdout, stderr) => {
              if (err) reject(new Error((stderr || err.message || "").trim().split(/\r?\n/).slice(-2).join(" | ")));
              else resolve(stdout);
            }
          );
        });
        let ver = "";
        try {
          ver = execFileSync("python", ["-m", "yt_dlp", "--version"], { encoding: "utf8", timeout: 8000 }).trim();
        } catch {}
        return sendJson(res, 200, { ok: true, version: ver });
      } catch (err) {
        return sendJson(res, 500, { error: `فشل تحديث yt-dlp: ${err.message}` });
      }
    }

    if (pathname.startsWith("/api/assets/upload/") && req.method === "POST") {
      const bucket = pathname.replace("/api/assets/upload/", "");
      if (!["music", "logo", "luts", "sfx"].includes(bucket)) {
        return sendJson(res, 400, { error: "Invalid asset category" });
      }
      const fname = safeFilename(decodeURIComponent(req.headers["x-filename"] || "asset.bin"));
      const dest = path.join(ASSETS_DIR, bucket, fname);
      const size = await saveRawUpload(req, dest);
      return sendJson(res, 200, { ok: true, name: fname, size });
    }

    const delAssetMatch = pathname.match(/^\/api\/assets\/(music|logo|luts)\/(.+)$/);
    if (delAssetMatch && req.method === "DELETE") {
      const target = path.join(ASSETS_DIR, delAssetMatch[1], safeFilename(delAssetMatch[2]));
      if (isInside(ASSETS_DIR, target) && fs.existsSync(target)) {
        fs.unlinkSync(target);
      }
      return sendJson(res, 200, { ok: true });
    }

    if (pathname === "/api/prompts" && req.method === "GET") {
      const loadPrompt = (f) => {
        const p = path.join(PROMPTS_DIR, f);
        return fs.existsSync(p) ? fs.readFileSync(p, "utf8") : "";
      };
      return sendJson(res, 200, {
        brandSetup: loadPrompt("01-brand-setup-pro.md"),
        editVideo: loadPrompt("02-edit-video-pro.md"),
        quickTweaks: loadPrompt("03-quick-tweaks.md"),
      });
    }

    if (pathname === "/api/projects" && req.method === "GET") {
      return sendJson(res, 200, { projects: listProjects() });
    }

    if (pathname === "/api/projects" && req.method === "POST") {
      const body = await readJsonBody(req);
      const slug = body.id ? safeSlug(body.id) : nextUniqueProjectSlug(body.title || "new-video");
      const dir = path.join(VIDEOS_DIR, slug);
      fs.mkdirSync(path.join(dir, "broll"), { recursive: true });
      fs.mkdirSync(path.join(dir, "work"), { recursive: true });
      const brand = readBrandConfig();
      const settings = {
        ...defaultProjectSettings(brand, body.title || slug, body.brandProfile),
        styleMode: body.styleMode || brand.defaults?.styleMode || "fast_hook",
        hookTitle: body.hookTitle || "",
      };
      fs.writeFileSync(path.join(dir, "settings.json"), JSON.stringify(settings, null, 2), "utf8");
      return sendJson(res, 200, { ok: true, project: inspectProject(slug) });
    }

    // 1-Step Quick Upload from Home Screen -> Auto-create project + save input.mp4
    if (pathname === "/api/projects/quick-upload" && req.method === "POST") {
      const origName = decodeURIComponent(req.headers["x-filename"] || "my-video.mp4");
      const brandProfile = decodeURIComponent(req.headers["x-brand-profile"] || "");
      const userTitle = req.headers["x-title"] ? decodeURIComponent(req.headers["x-title"]).trim() : "";
      const baseTitle = userTitle || path.basename(origName, path.extname(origName));
      const slug = nextUniqueProjectSlug(baseTitle);
      const dir = path.join(VIDEOS_DIR, slug);
      fs.mkdirSync(path.join(dir, "broll"), { recursive: true });
      fs.mkdirSync(path.join(dir, "work"), { recursive: true });
      const brand = readBrandConfig();
      const settings = defaultProjectSettings(brand, baseTitle, brandProfile);
      if (userTitle) {
        settings.hookTitle = userTitle;
      }
      fs.writeFileSync(path.join(dir, "settings.json"), JSON.stringify(settings, null, 2), "utf8");
      const size = await saveRawUpload(req, path.join(dir, "input.mp4"));
      return sendJson(res, 200, { ok: true, size, project: inspectProject(slug) });
    }

    // Import Local Video by Windows File Path (instant local copy for big files!)
    if (pathname === "/api/projects/import-local" && req.method === "POST") {
      const body = await readJsonBody(req);
      const rawPath = String(body.filePath || "").trim().replace(/^["']|["']$/g, "");
      if (!rawPath || !fs.existsSync(rawPath) || fs.statSync(rawPath).isDirectory()) {
        return sendJson(res, 400, { error: "المسار غير موجود أو ليس ملف فيديو صالح." });
      }
      const userTitle = String(body.title || "").trim();
      const baseTitle = userTitle || path.basename(rawPath, path.extname(rawPath));
      const slug = body.projectId && fs.existsSync(path.join(VIDEOS_DIR, body.projectId))
        ? body.projectId
        : nextUniqueProjectSlug(baseTitle);
      const dir = path.join(VIDEOS_DIR, slug);
      fs.mkdirSync(path.join(dir, "broll"), { recursive: true });
      fs.mkdirSync(path.join(dir, "work"), { recursive: true });
      if (!fs.existsSync(path.join(dir, "settings.json"))) {
        const brand = readBrandConfig();
        const settings = defaultProjectSettings(brand, baseTitle, body.brandProfile);
        if (userTitle) settings.hookTitle = userTitle;
        fs.writeFileSync(path.join(dir, "settings.json"), JSON.stringify(settings, null, 2), "utf8");
      }
      fs.copyFileSync(rawPath, path.join(dir, "input.mp4"));
      return sendJson(res, 200, { ok: true, project: inspectProject(slug) });
    }

    // Import Video Directly by URL (TikTok / Facebook / Reels / Shorts / Direct MP4) + Optional Instant Auto-Edit
    if (pathname === "/api/projects/import-url" && req.method === "POST") {
      const body = await readJsonBody(req);
      const videoUrl = String(body.url || "").trim();
      if (!/^https?:\/\/\S+/i.test(videoUrl)) {
        return sendJson(res, 400, { error: "الرابط غير صالح — يجب أن يبدأ بـ http:// أو https://" });
      }
      let hostHint = "url";
      try {
        hostHint = new URL(videoUrl).hostname.replace(/^www\./, "").split(".")[0] || "url";
      } catch {}
      const userTitle = (body.title || "").trim();
      const slug = nextUniqueProjectSlug(userTitle ? safeSlug(userTitle) : `${hostHint}-video`);
      const dir = path.join(VIDEOS_DIR, slug);
      fs.mkdirSync(path.join(dir, "broll"), { recursive: true });
      fs.mkdirSync(path.join(dir, "work"), { recursive: true });
      const brand = readBrandConfig();
      const settings = {
        ...defaultProjectSettings(brand, userTitle || "فيديو من رابط...", body.brandProfile),
        ...(userTitle ? { hookTitle: userTitle } : {}),
        sourceUrl: videoUrl,
        ...(body.styleMode ? { styleMode: body.styleMode } : {}),
        ...(body.renderQuality ? { renderQuality: body.renderQuality } : {}),
      };
      fs.writeFileSync(path.join(dir, "settings.json"), JSON.stringify(settings, null, 2), "utf8");
      const autoEdit = body.autoEdit !== false;
      const jobId = startUrlImportJob(slug, dir, videoUrl, autoEdit);
      return sendJson(res, 200, { ok: true, jobId, project: inspectProject(slug) });
    }

    const projMatch = pathname.match(/^\/api\/projects\/([^/]+)(?:\/(.+))?$/);
    if (projMatch) {
      const id = projMatch[1];
      const action = projMatch[2] || "";
      const dir = path.join(VIDEOS_DIR, id);
      if (!isInside(VIDEOS_DIR, dir) || !fs.existsSync(dir)) {
        return sendJson(res, 404, { error: "Project not found" });
      }

      if (!action && req.method === "GET") {
        return sendJson(res, 200, { project: inspectProject(id) });
      }

      if (!action && req.method === "DELETE") {
        const freedBytes = dirSizeBytes(dir);
        fs.rmSync(dir, { recursive: true, force: true });
        return sendJson(res, 200, { ok: true, freedBytes });
      }

      if (action === "settings" && req.method === "POST") {
        const body = await readJsonBody(req);
        body.updatedAt = new Date().toISOString();
        fs.writeFileSync(path.join(dir, "settings.json"), JSON.stringify(body, null, 2), "utf8");
        return sendJson(res, 200, { ok: true, project: inspectProject(id) });
      }

      if (action === "timeline" && req.method === "POST") {
        const body = await readJsonBody(req);
        fs.mkdirSync(path.join(dir, "work"), { recursive: true });
        fs.writeFileSync(path.join(dir, "work", "timeline_data.json"), JSON.stringify(body, null, 2), "utf8");
        return sendJson(res, 200, { ok: true, project: inspectProject(id) });
      }

      if (action === "prompt" && req.method === "GET") {
        const project = inspectProject(id);
        const brand = readBrandConfig();
        return sendJson(res, 200, { prompt: buildTailoredPrompt(project, brand) });
      }

      if (action === "upload/input" && req.method === "POST") {
        const dest = path.join(dir, "input.mp4");
        const size = await saveRawUpload(req, dest);
        return sendJson(res, 200, { ok: true, size, project: inspectProject(id) });
      }

      if (action === "upload/broll" && req.method === "POST") {
        const fname = safeFilename(decodeURIComponent(req.headers["x-filename"] || "clip.png"));
        const dest = path.join(dir, "broll", fname);
        const size = await saveRawUpload(req, dest);
        return sendJson(res, 200, {
          ok: true,
          name: fname,
          size,
          url: `/media/videos/${encodeURIComponent(id)}/broll/${encodeURIComponent(fname)}`,
          project: inspectProject(id),
        });
      }

      if (action === "crop-preview" && req.method === "POST") {
        const body = await readJsonBody(req);
        const inputPath = path.join(dir, "input.mp4");
        if (!fs.existsSync(inputPath)) {
          return sendJson(res, 400, { error: "الفيديو الخام غير موجود." });
        }
        const workDir = path.join(dir, "work");
        fs.mkdirSync(workDir, { recursive: true });
        const outPreview = path.join(workDir, "crop_preview.mp4");
        const args = [
          path.join(ROOT, "scripts", "color_grade.py"),
          inputPath,
          outPreview,
          "--preset", "natural",
          "--vertical",
          "--preview",
          "--fit-mode", String(body.fitMode || "cover"),
          "--zoom", String(Number(body.cropZoom || 1)),
          "--pan-x", String(Number(body.cropPanX || 0)),
          "--pan-y", String(Number(body.cropPanY || 0)),
          "--crop-top", String(Number(body.cropTop || 0)),
          "--crop-bottom", String(Number(body.cropBottom || 0)),
          "--crop-left", String(Number(body.cropLeft || 0)),
          "--crop-right", String(Number(body.cropRight || 0)),
        ];
        try {
          await new Promise((resolve, reject) => {
            execFile("python", args, { cwd: ROOT, encoding: "utf8", timeout: 180000, maxBuffer: 8 * 1024 * 1024 }, (err, stdout, stderr) => {
              if (err) {
                const msg = (stderr || err.message || "").trim().split(/\r?\n/).slice(-3).join(" | ");
                reject(new Error(msg || "فشل تنفيذ FFmpeg"));
              } else {
                resolve(stdout);
              }
            });
          });
        } catch (err) {
          return sendJson(res, 500, { error: `فشل تطبيق معاينة القصّ: ${err.message}` });
        }
        return sendJson(res, 200, {
          ok: true,
          previewUrl: `/media/videos/${encodeURIComponent(id)}/work/crop_preview.mp4?t=${Date.now()}`,
        });
      }

      if (action === "upload/voice" && req.method === "POST") {
        const origName = safeFilename(decodeURIComponent(req.headers["x-filename"] || "voice.mp3"));
        const ext = path.extname(origName).toLowerCase() || ".mp3";
        const workDir = path.join(dir, "work");
        fs.mkdirSync(workDir, { recursive: true });
        for (const f of fs.readdirSync(workDir)) {
          if (f.startsWith("custom_voice_raw")) {
            try { fs.unlinkSync(path.join(workDir, f)); } catch {}
          }
        }
        const fname = `custom_voice_raw${ext}`;
        const dest = path.join(workDir, fname);
        const size = await saveRawUpload(req, dest);
        return sendJson(res, 200, {
          ok: true,
          size,
          voiceUrl: `/media/videos/${encodeURIComponent(id)}/work/${encodeURIComponent(fname)}`,
        });
      }

      if (action === "tts" && req.method === "POST") {
        const body = await readJsonBody(req);
        const text = String(body.text || "").trim();
        if (!text) {
          return sendJson(res, 400, { error: "اكتب النص العربي أولاً لتوليد الصوت." });
        }
        const workDir = path.join(dir, "work");
        fs.mkdirSync(workDir, { recursive: true });
        const outWav = path.join(workDir, "tts_voice.wav");
        const wordsJson = path.join(workDir, "tts_words.json");
        const voice = String(body.voice || "salma");
        const rate = String(body.rate || "+0%");
        const preset = String(body.voicePreset || "studio");
        try {
          execFileSync(
            "python",
            [
              path.join(ROOT, "scripts", "tts_arabic.py"),
              `--text=${text}`,
              `--out=${outWav}`,
              `--words-out=${wordsJson}`,
              `--voice=${voice}`,
              `--rate=${rate}`,
              `--preset=${preset}`,
            ],
            { cwd: ROOT, encoding: "utf8", timeout: 45000, env: { ...process.env, PYTHONIOENCODING: "utf-8" } }
          );
        } catch (err) {
          const rawErr = String(err.stderr || err.message || "").trim();
          const lastLine = rawErr.split(/\r?\n/).filter(Boolean).pop() || "خطأ غير معروف";
          return sendJson(res, 500, { error: `فشل توليد الصوت: ${lastLine}` });
        }

        if (body.updateCaptions && fs.existsSync(wordsJson)) {
          try {
            const words = JSON.parse(fs.readFileSync(wordsJson, "utf8"));
            const tlPath = path.join(workDir, "timeline_data.json");
            const tl = fs.existsSync(tlPath) ? JSON.parse(fs.readFileSync(tlPath, "utf8")) : { duration: 15, captions: [] };
            const chunks = [];
            for (let i = 0; i < words.length; i += 4) {
              const grp = words.slice(i, i + 4);
              if (!grp.length) continue;
              chunks.push({
                id: chunks.length,
                start: grp[0].start,
                end: grp[grp.length - 1].end,
                text: grp.map((w) => w.word).join(" "),
                highlight: "",
                broll: "",
                zoom: false,
                words: grp,
              });
            }
            if (chunks.length) {
              tl.captions = chunks;
              tl.full_text = words.map((w) => w.word).join(" ");
              fs.writeFileSync(tlPath, JSON.stringify(tl, null, 2), "utf8");
            }
          } catch {}
        }

        return sendJson(res, 200, {
          ok: true,
          voiceUrl: `/media/videos/${encodeURIComponent(id)}/work/tts_voice.wav?t=${Date.now()}`,
        });
      }

      if (action.startsWith("broll/") && req.method === "DELETE") {
        const fname = safeFilename(action.replace("broll/", ""));
        const target = path.join(dir, "broll", fname);
        if (isInside(dir, target) && fs.existsSync(target)) fs.unlinkSync(target);
        return sendJson(res, 200, { ok: true, project: inspectProject(id) });
      }

      if (action === "save-export" && req.method === "POST") {
        const outMp4 = path.join(dir, "output.mp4");
        if (!fs.existsSync(outMp4)) {
          return sendJson(res, 400, { error: "الفيديو النهائي غير جاهز بعد — شغّل الرندر أولاً." });
        }
        const brand = readBrandConfig();
        const settingsPath = path.join(dir, "settings.json");
        const settings = fs.existsSync(settingsPath) ? JSON.parse(fs.readFileSync(settingsPath, "utf8")) : {};
        const tlPath = path.join(dir, "work", "timeline_data.json");
        const timeline = fs.existsSync(tlPath) ? JSON.parse(fs.readFileSync(tlPath, "utf8")) : {};
        const prof = resolveBrandProfile(brand, settings.brandProfile);
        const exportDir = String(brand?.defaults?.exportFolder || "D:\\غناوي هلنا").trim() || "D:\\غناوي هلنا";
        fs.mkdirSync(exportDir, { recursive: true });

        const baseName = buildRealisticExportName(settings, timeline, prof);
        const fileName = `${baseName}.mp4`;
        const savedPath = path.join(exportDir, fileName);
        fs.copyFileSync(outMp4, savedPath);

        if (isGenericVideoName(settings.title)) settings.title = baseName;
        settings.exportFileName = fileName;
        settings.lastExportPath = savedPath;
        fs.writeFileSync(settingsPath, JSON.stringify(settings, null, 2), "utf8");

        return sendJson(res, 200, {
          ok: true,
          fileName,
          savedPath,
          exportFolder: exportDir,
          project: inspectProject(id),
        });
      }

      if (action === "run" && req.method === "POST") {
        const body = await readJsonBody(req);
        const inputPath = path.join(dir, "input.mp4");
        if (!fs.existsSync(inputPath)) {
          return sendJson(res, 400, { error: "ارفع الفيديو الخام (input.mp4) أولاً قبل تشغيل المونتاج." });
        }
        const task = body.task || "auto_full";
        const modeMap = { auto_full: "full", rerender: "rerender", prep_all: "prep" };
        const mode = modeMap[task] || "full";
        const jobId = startAutoEditJob(dir, mode);
        return sendJson(res, 200, { ok: true, jobId });
      }
    }

    if (pathname.startsWith("/api/jobs/") && req.method === "GET") {
      const jobId = pathname.replace("/api/jobs/", "");
      const job = jobs.get(jobId);
      if (!job) return sendJson(res, 404, { error: "Job not found" });
      return sendJson(res, 200, job);
    }

    if (pathname === "/api/open-folder" && req.method === "POST") {
      const body = await readJsonBody(req);
      const target = body.projectId ? path.join(VIDEOS_DIR, body.projectId) : ROOT;
      if (process.platform === "win32" && fs.existsSync(target)) {
        spawn("explorer.exe", [target], { detached: true, stdio: "ignore" }).unref();
      }
      return sendJson(res, 200, { ok: true });
    }

    if (pathname.startsWith("/media/")) {
      const rel = pathname.replace("/media/", "");
      const fullPath = path.resolve(ROOT, rel);
      if (!isInside(ROOT, fullPath)) {
        res.writeHead(403);
        res.end("Forbidden");
        return;
      }
      return serveFileWithRange(req, res, fullPath);
    }

    if (pathname.startsWith("/fonts/")) {
      const fname = path.basename(pathname);
      return serveFileWithRange(req, res, path.join(ASSETS_DIR, "fonts", fname));
    }

    const staticRel = pathname === "/" ? "index.html" : pathname.replace(/^\/+/, "");
    const staticPath = path.resolve(PUBLIC_DIR, staticRel);
    if (!isInside(PUBLIC_DIR, staticPath) && staticPath !== path.join(PUBLIC_DIR, "index.html")) {
      res.writeHead(403);
      res.end("Forbidden");
      return;
    }
    return serveFileWithRange(req, res, staticPath);
  } catch (err) {
    console.error(err);
    sendJson(res, 500, { error: err.message || "Internal server error" });
  }
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`Avesta AI Video Studio v2 running at http://localhost:${PORT}`);
});
