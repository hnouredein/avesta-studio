/* =============================================
   Avesta AI Video Studio — app.js (Refactored)
   Simple one-button workflow:
   Upload/URL → auto-edit → progress modal
   ============================================= */

"use strict";

// ── State ──────────────────────────────────────────────────────────────────────
const state = {
  brand: null,
  activeBrandProfile: "ghinawi_halna",
  assets: null,
  projects: [],
  status: null,
  currentJob: null,       // { jobId, projectId }
  pollTimer: null,
  selectedFile: null,     // File object from input
  selectedLocalFile: null, // { path, name, size } from Electron native Downloads picker
  editor: {
    project: null,
    overlays: [],
    selectedId: null,
    drawMode: false,
  },
};

// ── Helpers ────────────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

function showToast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove("show"), 3500);
}

async function api(url, opts = {}) {
  const res = await fetch(url, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "حدث خطأ");
  return data;
}

function formatBytes(b) {
  if (!b) return "0 KB";
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1048576).toFixed(2)} MB`;
}

function statusBadge(status) {
  switch (status) {
    case "done":    return { cls: "badge-done",    label: "✅ جاهز للنشر" };
    case "prepped": return { cls: "badge-prepped", label: "🎚️ معالجة أولية" };
    case "raw":     return { cls: "badge-raw",     label: "📹 جاهز للمونتاج" };
    default:        return { cls: "badge-empty",   label: "📂 بانتظار الفيديو" };
  }
}

function hexToRgba(hex, alpha) {
  const c = String(hex || "#F5C542").replace("#", "");
  if (c.length !== 6) return `rgba(245,197,66,${alpha})`;
  return `rgba(${parseInt(c.slice(0,2),16)},${parseInt(c.slice(2,4),16)},${parseInt(c.slice(4,6),16)},${alpha})`;
}

// ── View Navigation ────────────────────────────────────────────────────────────
const VIEW_META = {
  home:     { title: "الرئيسية", sub: "ارفع فيديوك وبضغطة زر واحدة يخرج جاهزاً للنشر" },
  projects: { title: "مشاريعي", sub: "فيديوهاتك المنتجة — حمّل أو عدّل أو افتح الفولدر" },
  brand:    { title: "الهوية", sub: "إعدادات البراند — تُعمل مرة واحدة وتتطبق على كل فيديو" },
  editor:   { title: "تعديل بعد المعالجة", sub: "أضف نصوصاً أو اخفِ كلاماً موجوداً بنصك الجديد ثم اضغط تطبيق التعديلات" },
};

function switchView(viewName) {
  document.querySelectorAll(".nav-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.view === viewName);
  });
  document.querySelectorAll(".view-section").forEach((el) => {
    el.classList.toggle("active", el.id === `view-${viewName}`);
  });
  const meta = VIEW_META[viewName] || VIEW_META.home;
  $("pageTitle").textContent = meta.title;
  $("pageSubtitle").textContent = meta.sub;
}

// ── Brand / Theme ──────────────────────────────────────────────────────────────
function getBrandProfile(id) {
  const brand = state.brand || {};
  const chosenId = (id || state.activeBrandProfile || "ghinawi_halna").trim();
  const found = (brand.profiles || []).find((p) => p && p.id === chosenId);
  if (!found) return { ...brand, id: chosenId, accountName: brand.accountName || "غناوي هلنا", colors: brand.colors || {} };
  return { ...brand, ...found, colors: { ...(brand.colors || {}), ...(found.colors || {}) } };
}

function getLogoUrl(prof) {
  const logos = state.assets?.logo || [];
  if (prof?.logoFile) {
    const exact = logos.find((l) => l.name === prof.logoFile);
    if (exact) return exact.url;
    return `/media/assets/logo/${encodeURIComponent(prof.logoFile)}`;
  }
  return logos[0]?.url || "";
}

function applyTheme() {
  const prof = getBrandProfile(state.activeBrandProfile);
  const accent = prof.colors?.accent || "#F5C542";
  document.documentElement.dataset.brandProfile = state.activeBrandProfile || "ghinawi_halna";
  document.documentElement.style.setProperty("--accent", accent);
  document.documentElement.style.setProperty("--accent-soft", hexToRgba(accent, 0.13));
  document.documentElement.style.setProperty("--accent-glow", hexToRgba(accent, 0.28));

  const name = prof.accountName || "غناوي هلنا";
  $("sidebarBrandName").textContent = name;
  document.title = `${name} — استوديو المونتاج`;

  const mark = $("sidebarBrandMark");
  const logoUrl = getLogoUrl(prof);
  if (mark) {
    if (logoUrl) {
      mark.innerHTML = `<img src="${logoUrl}?t=${Date.now()}" alt="Logo" />`;
    } else {
      mark.textContent = name.trim().charAt(0) || "غ";
    }
  }

  // sync all brand-sw-btn
  document.querySelectorAll(".brand-sw-btn[data-profile]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.profile === state.activeBrandProfile);
  });
}

function switchBrandProfile(profileId) {
  state.activeBrandProfile = profileId;
  applyTheme();
}

// ── Health Status ──────────────────────────────────────────────────────────────
function renderHealth() {
  const s = state.status || {};
  const ok = s.ffmpeg?.ok && s.node?.ok;
  const dot = $("sidebarHealthDot");
  const txt = $("sidebarHealthText");
  if (dot) dot.className = "dot" + (ok ? "" : " warn");
  if (txt) txt.textContent = ok ? "النظام جاهز ✅" : "تحقق من الأدوات ⚠️";
}

// ── Projects Rendering ─────────────────────────────────────────────────────────
function renderProjects() {
  const grid = $("projectsGrid");
  if (!grid) return;

  const count = $("navProjectsCount");
  if (count) count.textContent = state.projects.length;

  if (!state.projects.length) {
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🎬</div>
        <div>لا توجد مشاريع بعد</div>
        <div class="empty-sub">ارفع فيديوك من الرئيسية وسيبدأ المونتاج التلقائي فوراً</div>
      </div>`;
    return;
  }

  grid.innerHTML = state.projects
    .slice()
    .reverse()
    .map((p) => {
      const { cls, label } = statusBadge(p.status);
      const title = p.settings?.title || p.title || p.id;
      const thumb = p.files?.outputUrl
        ? `<video src="${p.files.outputUrl}" muted loop preload="metadata" onmouseenter="this.play()" onmouseleave="this.pause()"></video>`
        : (p.files?.coverUrl ? `<img src="${p.files.coverUrl}" alt="Cover" />` : `<span>🎬</span>`);
      const playBtn = p.files?.outputUrl
        ? `<button class="btn-proj" onclick="playProjectVideo('${p.id}', '${p.files.outputUrl}', '${encodeURIComponent(title)}')">▶️ تشغيل</button>`
        : '';
      const dlBtn = p.files?.outputUrl
        ? `<button class="btn-proj primary" onclick="saveProjectToExportFolder('${p.id}')" title="حفظ مباشر في D:\\غناوي هلنا باسم واقعي للفيديو">💾 حفظ</button>`
        : `<button class="btn-proj primary" onclick="runAutoEdit('${p.id}')">🚀 انتج الآن</button>`;
      return `
        <div class="proj-card">
          <div class="proj-thumb">${thumb}</div>
          <div class="proj-info">
            <div class="proj-name" title="${title}">${title}</div>
            <div style="display:flex; align-items:center; justify-content:space-between; gap:6px;">
              <span class="badge ${cls}">${label}</span>
              <span style="font-size:11px; color:var(--text-dim); direction:ltr;">${formatBytes(p.diskBytes || 0)}</span>
            </div>
          </div>
          <div class="proj-actions">
            ${playBtn}
            ${dlBtn}
            <button class="btn-proj" onclick="openEditor('${p.id}')" title="تعديل وإضافة نصوص أو إخفاء كلام">✏️ تعديل</button>
            <button class="btn-proj" onclick="openFolder('${p.id}')" title="فتح مجلد المشروع">📂</button>
            <button class="btn-proj" style="color:var(--red);" onclick="deleteProject('${p.id}', '${encodeURIComponent(title)}')" title="حذف الفيديو وكل ملفاته من الهارد">🗑️</button>
          </div>
        </div>`;
    })
    .join("");
}

function playProjectVideo(id, url, titleEncoded) {
  const title = decodeURIComponent(titleEncoded || id);
  const modal = $("progressModal");
  if (!modal) return;
  modal.style.display = "flex";
  $("modalTitle").textContent = `🎬 ${title}`;
  $("progressWrap").style.display = "none";
  $("progressStage").textContent = "معاينة الفيديو النهائي";
  $("consoleLog").style.display = "none";

  const previewWrap = $("modalPreviewWrap");
  const videoPlayer = $("modalVideoPlayer");
  if (previewWrap && videoPlayer) {
    videoPlayer.src = url;
    previewWrap.style.display = "flex";
    videoPlayer.play().catch(() => {});
  }

  const actionsEl = $("modalActions");
  if (actionsEl) {
    actionsEl.style.display = "flex";
    const dlBtn = $("btnDownload");
    const editBtn = $("btnModalEdit");
    const folderBtn = $("btnModalOpenFolder");
    if (dlBtn) {
      dlBtn.removeAttribute("href");
      dlBtn.removeAttribute("download");
      dlBtn.textContent = "💾 حفظ في غناوي هلنا";
      dlBtn.style.display = "inline-flex";
      dlBtn.onclick = (e) => {
        e.preventDefault();
        saveProjectToExportFolder(id);
      };
    }
    if (editBtn) {
      editBtn.onclick = () => {
        hideProgressModal();
        openEditor(id);
      };
    }
    if (folderBtn) {
      folderBtn.onclick = () => openFolder(id);
    }
  }
}

// ── Run Auto-Edit for a project ────────────────────────────────────────────────
async function runAutoEdit(projectId) {
  try {
    showToast("🎬 جاري بدء المونتاج...");
    const { jobId } = await api(`/api/projects/${projectId}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task: "auto_full" }),
    });
    state.currentJob = { jobId, projectId };
    showProgressModal(projectId);
    startPolling(jobId);
  } catch (err) {
    showToast("❌ " + err.message);
  }
}

async function saveProjectToExportFolder(projectId) {
  if (!projectId) return;
  try {
    showToast("💾 جاري الحفظ مباشرة في فولدر غناوي هلنا...");
    const res = await api(`/api/projects/${encodeURIComponent(projectId)}/save-export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    await refreshProjects();
    showToast(`✅ تم الحفظ: ${res.savedPath}`);
  } catch (err) {
    showToast("❌ تعذّر الحفظ: " + err.message);
  }
}

async function openFolder(projectId) {
  try {
    await api("/api/open-folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ projectId }),
    });
  } catch (e) { /* ignore */ }
}

async function deleteProject(projectId, titleEncoded) {
  const title = titleEncoded ? decodeURIComponent(titleEncoded) : projectId;
  if (!confirm(`هل أنت متأكد من حذف "${title}"؟\nسيتم مسح الفيديو وكل ملفاته نهائياً من الهارد لتوفير المساحة.`)) {
    return;
  }
  try {
    const res = await api(`/api/projects/${encodeURIComponent(projectId)}`, { method: "DELETE" });
    showToast(`🗑️ تم الحذف نهائياً وتوفير ${formatBytes(res.freedBytes || 0)} من المساحة!`);
    if (state.editor.project?.id === projectId) {
      const vid = $("edVideoPlayer");
      if (vid) { vid.pause(); vid.src = ""; }
      state.editor.project = null;
      switchView("projects");
    }
    await refreshProjects();
  } catch (err) {
    showToast("❌ تعذّر الحذف: " + err.message);
  }
}

// ── Home View: File / URL Handling ─────────────────────────────────────────────
function setupHomeView() {
  const dropzone   = $("mainDropzone");
  const fileInput  = $("fileInput");
  const urlInput   = $("urlInput");
  const btnChoose  = $("btnChooseFile");
  const btnProduce = $("btnProduce");
  const hint       = $("homeHint");

  // Native Downloads folder picker (Electron) with browser <input> fallback
  const pickVideoFile = async () => {
    if (window.electronAPI?.pickVideoFromDownloads) {
      const picked = await window.electronAPI.pickVideoFromDownloads();
      if (!picked || !picked.path) return;
      state.selectedLocalFile = picked;
      state.selectedFile = null;
      if (fileInput) fileInput.value = "";
      if (urlInput) urlInput.value = "";
      dropzone?.classList.add("has-file");
      dropzone?.classList.remove("drag-over");
      if (hint) hint.textContent = `✅ ${picked.name} (${formatBytes(picked.size)}) — اضغط "افتح في الاستوديو"`;
      return;
    }
    fileInput?.click();
  };
  state.pickVideoFile = pickVideoFile;

  // Open file dialog (always directly in Downloads when in Desktop App)
  if (btnChoose) btnChoose.addEventListener("click", (e) => { e.stopPropagation(); pickVideoFile(); });

  // Prevent clicking inside URL box from opening local file picker!
  const urlRow = dropzone?.querySelector(".url-row");
  if (urlRow) urlRow.addEventListener("click", (e) => e.stopPropagation());
  if (urlInput) urlInput.addEventListener("click", (e) => e.stopPropagation());

  // Click empty dropzone area only to pick file
  if (dropzone) dropzone.addEventListener("click", (e) => {
    if (e.target.closest(".url-row, input, button, label, a")) return;
    pickVideoFile();
  });

  // File input change
  if (fileInput) fileInput.addEventListener("change", () => {
    const f = fileInput.files?.[0];
    if (!f) return;
    state.selectedFile = f;
    state.selectedLocalFile = null;
    urlInput.value = "";
    dropzone.classList.add("has-file");
    dropzone.classList.remove("drag-over");
    if (hint) hint.textContent = `✅ ${f.name} (${formatBytes(f.size)}) — اضغط "انتج الآن"`;
  });

  // URL input change
  if (urlInput) urlInput.addEventListener("input", () => {
    if (urlInput.value.trim()) {
      state.selectedFile = null;
      state.selectedLocalFile = null;
      fileInput.value = "";
      dropzone.classList.remove("has-file");
      if (hint) hint.textContent = `🔗 رابط محدد — اضغط "انتج الآن"`;
    }
  });

  // Drag & Drop
  if (dropzone) {
    dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("drag-over"); });
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("drag-over"));
    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.classList.remove("drag-over");
      const f = e.dataTransfer.files?.[0];
      if (f && f.type.startsWith("video/")) {
        state.selectedFile = f;
        state.selectedLocalFile = null;
        urlInput.value = "";
        dropzone.classList.add("has-file");
        if (hint) hint.textContent = `✅ ${f.name} (${formatBytes(f.size)}) — اضغط "انتج الآن"`;
      } else {
        showToast("⚠️ الملف ليس فيديو صالح");
      }
    });
  }

  // Produce buttons: Default = Open in Studio before render; Secondary = Instant auto-edit
  const triggerHomeAction = async (openEditorFirst, activeBtn, defaultLabel) => {
    const url = urlInput?.value.trim();
    const file = state.selectedFile;
    const localFile = state.selectedLocalFile;

    if (!file && !localFile && !url) {
      showToast("⚠️ اختر فيديو أو الصق رابطاً أولاً");
      return;
    }

    const otherBtn = openEditorFirst ? $("btnProduceInstant") : btnProduce;
    if (activeBtn) {
      activeBtn.disabled = true;
      activeBtn.textContent = "⏳ جاري التحضير...";
    }
    if (otherBtn) otherBtn.disabled = true;

    try {
      if (localFile) {
        await handleLocalPathImport(localFile.path, openEditorFirst);
      } else if (file) {
        await handleFileUpload(file, openEditorFirst);
      } else {
        await handleUrlImport(url, openEditorFirst);
      }
    } catch (err) {
      showToast("❌ " + err.message);
    } finally {
      if (activeBtn) {
        activeBtn.disabled = false;
        activeBtn.textContent = defaultLabel;
      }
      if (otherBtn) otherBtn.disabled = false;
    }
  };

  if (btnProduce) {
    btnProduce.addEventListener("click", () => triggerHomeAction(true, btnProduce, "🎬 افتح في الاستوديو للتعديل ثم الرندر"));
  }
  const btnProduceInstant = $("btnProduceInstant");
  if (btnProduceInstant) {
    btnProduceInstant.addEventListener("click", () => triggerHomeAction(false, btnProduceInstant, "⚡ مونتاج فوري تلقائي"));
  }

  $("btnRefreshDownloads")?.addEventListener("click", () => loadRecentDownloads(true));
  window.addEventListener("focus", () => {
    if ($("view-home")?.classList.contains("active")) loadRecentDownloads(false);
  });
}

async function loadRecentDownloads(showFeedback = false) {
  const list = $("recentDownloadsList");
  if (!list) return;
  try {
    const { files } = await api("/api/recent-downloads");
    if (!files || !files.length) {
      list.innerHTML = `<div class="recent-dl-empty">لا توجد فيديوهات حديثة في مجلد التنزيلات — أي فيديو تحفظه من المتصفح سيظهر هنا فوراً!</div>`;
      return;
    }
    list.innerHTML = files.map((f) => {
      const safeName = String(f.name || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      const encPath = encodeURIComponent(f.path);
      return `
        <div class="recent-dl-item">
          <div class="recent-dl-meta">
            <div class="recent-dl-name" title="${safeName}">🎬 ${safeName}</div>
            <div class="recent-dl-sub">📂 ${f.folder} · <span class="ltr">${formatBytes(f.sizeBytes)}</span></div>
          </div>
          <div class="recent-dl-btns">
            <button type="button" class="btn btn-accent btn-sm" data-radar-edit="${encPath}">🎬 تعديل</button>
            <button type="button" class="btn btn-sm" data-radar-instant="${encPath}" title="مونتاج فوري تلقائي">⚡</button>
          </div>
        </div>`;
    }).join("");

    list.querySelectorAll("[data-radar-edit]").forEach((btn) => {
      btn.addEventListener("click", () => importLocalFromRadar(decodeURIComponent(btn.dataset.radarEdit), true, btn));
    });
    list.querySelectorAll("[data-radar-instant]").forEach((btn) => {
      btn.addEventListener("click", () => importLocalFromRadar(decodeURIComponent(btn.dataset.radarInstant), false, btn));
    });
    if (showFeedback) showToast("🔄 تم تحديث قائمة الفيديوهات المحمّلة");
  } catch {
    list.innerHTML = `<div class="recent-dl-empty">تعذّر قراءة مجلد التنزيلات.</div>`;
  }
}

async function importLocalFromRadar(filePath, openEditorFirst, btnEl) {
  if (btnEl) btnEl.disabled = true;
  try {
    showToast("📥 جاري استيراد الفيديو فوراً...");
    const { project } = await api("/api/projects/import-local", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filePath,
        brandProfile: state.activeBrandProfile || "ghinawi_halna",
      }),
    });
    await refreshProjects();
    if (openEditorFirst) {
      showToast("✅ تم الاستيراد — عدّل واقصّ الفيديو كما تريد!");
      await openEditor(project.id);
    } else {
      showToast("✅ تم الاستيراد — جاري بدء المونتاج التلقائي...");
      await runAutoEdit(project.id);
    }
  } catch (err) {
    showToast("❌ " + err.message);
  } finally {
    if (btnEl) btnEl.disabled = false;
  }
}

// ── Local Disk Import (from Electron Downloads Picker) ─────────────────────────
async function handleLocalPathImport(filePath, openEditorFirst = true) {
  showToast("📥 جاري استيراد الفيديو من جهازك...");
  const title = $("titleInput")?.value.trim();
  const { project } = await api("/api/projects/import-local", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filePath,
      brandProfile: state.activeBrandProfile || "ghinawi_halna",
      title: title || undefined,
    }),
  });
  resetHomeForm();
  await refreshProjects();
  if (openEditorFirst) {
    showToast("✅ تم الاستيراد — عدّل واقصّ الفيديو كما تريد ثم اضغط ابدأ الرندر!");
    await openEditor(project.id);
  } else {
    showToast("✅ تم الاستيراد — جاري بدء المونتاج التلقائي...");
    await runAutoEdit(project.id);
  }
}

// ── Upload File → Open Editor (default) OR Instant Auto-Edit ───────────────────
async function handleFileUpload(file, openEditorFirst = true) {
  showToast("📤 جاري رفع الفيديو...");

  const headers = {
    "x-filename": encodeURIComponent(file.name),
    "x-brand-profile": state.activeBrandProfile || "ghinawi_halna",
  };

  const title = $("titleInput")?.value.trim();
  if (title) headers["x-title"] = encodeURIComponent(title);

  const { project } = await api("/api/projects/quick-upload", {
    method: "POST",
    headers,
    body: file,
  });

  resetHomeForm();
  await refreshProjects();

  if (openEditorFirst) {
    showToast("✅ تم الرفع — عدّل واقصّ الفيديو كما تريد ثم اضغط ابدأ الرندر!");
    await openEditor(project.id);
  } else {
    showToast("✅ تم الرفع — جاري بدء المونتاج التلقائي...");
    await runAutoEdit(project.id);
  }
}

// ── Import URL → Download then Open Editor (default) OR Instant Auto-Edit ──────
async function handleUrlImport(url, openEditorFirst = true) {
  showToast("🔗 جاري تحميل الفيديو من الرابط...");

  const title = $("titleInput")?.value.trim();
  const { project, jobId } = await api("/api/projects/import-url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url,
      brandProfile: state.activeBrandProfile || "ghinawi_halna",
      title: title || undefined,
      autoEdit: !openEditorFirst,
    }),
  });

  resetHomeForm();
  refreshProjects();

  state.currentJob = { jobId, projectId: project.id, openEditorOnDone: openEditorFirst };
  showProgressModal(project.id);
  if (openEditorFirst) {
    $("modalTitle").textContent = "⬇️ جاري تحميل الفيديو للتعديل...";
  }
  startPolling(jobId);
}

function resetHomeForm() {
  state.selectedFile = null;
  state.selectedLocalFile = null;
  if ($("fileInput")) $("fileInput").value = "";
  if ($("urlInput")) $("urlInput").value = "";
  if ($("titleInput")) $("titleInput").value = "";
  const dz = $("mainDropzone");
  if (dz) dz.classList.remove("has-file", "drag-over");
  if ($("homeHint")) $("homeHint").textContent = `ارفع الفيديو أو الصق رابطاً — يفتح أمامك فوراً للقصّ والتعديل قبل الرندر`;
}

// ── Progress Modal ─────────────────────────────────────────────────────────────
function showProgressModal(projectId) {
  const modal = $("progressModal");
  if (!modal) return;
  modal.style.display = "flex";
  $("progressFill").style.width = "0%";
  $("progressPct").textContent = "0%";
  $("progressStage").textContent = "تهيئة المحرك والمونتاج التلقائي...";
  $("consoleLog").textContent = "";
  $("modalTitle").textContent = "🎬 جاري المونتاج التلقائي...";
  if ($("progressWrap")) $("progressWrap").style.display = "flex";
  if ($("consoleLog")) $("consoleLog").style.display = "block";
  if ($("modalActions")) $("modalActions").style.display = "none";
  if ($("modalErrorActions")) $("modalErrorActions").style.display = "none";
  if ($("modalPreviewWrap")) {
    $("modalPreviewWrap").style.display = "none";
    const vp = $("modalVideoPlayer");
    if (vp) { vp.pause(); vp.src = ""; }
  }
}

function hideProgressModal() {
  const modal = $("progressModal");
  if (modal) modal.style.display = "none";
  const vp = $("modalVideoPlayer");
  if (vp) { vp.pause(); vp.src = ""; }
  stopPolling();
}

function appendLog(msg) {
  const el = $("consoleLog");
  if (!el) return;
  el.textContent += msg + "\n";
  el.scrollTop = el.scrollHeight;
}

function updateProgress(pct, stage) {
  const fill = $("progressFill");
  const pctEl = $("progressPct");
  const stageEl = $("progressStage");
  if (fill) fill.style.width = `${Math.min(100, Math.max(0, pct))}%`;
  if (pctEl) pctEl.textContent = `${Math.min(100, Math.max(0, Math.round(pct)))}%`;
  if (stageEl) stageEl.textContent = stage || "";
}

function onJobDone(job) {
  stopPolling();
  const projectId = state.currentJob?.projectId;
  const openEditorOnDone = Boolean(state.currentJob?.openEditorOnDone);

  if (openEditorOnDone && projectId) {
    hideProgressModal();
    refreshProjects();
    showToast("✅ تم تحميل الفيديو — عدّل واقصّ كما تريد ثم اضغط ابدأ الرندر!");
    openEditor(projectId);
    return;
  }

  updateProgress(100, "✅ اكتمل المونتاج بنجاح!");
  $("modalTitle").textContent = "🎉 الفيديو جاهز للنشر!";
  appendLog("\n✅ تم بنجاح! تم تطبيق الهوك والكادر والترجمة والألوان والموسيقى.\n");

  const outputUrl = job.outputUrl || (projectId ? `/media/videos/${projectId}/output.mp4` : null);

  // Show live video preview inside modal
  const previewWrap = $("modalPreviewWrap");
  const videoPlayer = $("modalVideoPlayer");
  if (previewWrap && videoPlayer && outputUrl) {
    videoPlayer.src = `${outputUrl}?t=${Date.now()}`;
    previewWrap.style.display = "flex";
  }

  // Show download/view actions
  const actionsEl = $("modalActions");
  if (actionsEl) {
    actionsEl.style.display = "flex";
    const dlBtn = $("btnDownload");
    const editBtn = $("btnModalEdit");
    const viewBtn = $("btnViewProject");
    const folderBtn = $("btnModalOpenFolder");

    if (dlBtn && projectId) {
      dlBtn.removeAttribute("href");
      dlBtn.removeAttribute("download");
      dlBtn.textContent = "💾 حفظ في D:\\غناوي هلنا";
      dlBtn.style.display = "inline-flex";
      dlBtn.onclick = (e) => {
        e.preventDefault();
        saveProjectToExportFolder(projectId);
      };
    }

    if (editBtn && projectId) {
      editBtn.onclick = () => {
        hideProgressModal();
        openEditor(projectId);
      };
    }

    if (folderBtn && projectId) {
      folderBtn.onclick = () => openFolder(projectId);
    }

    if (viewBtn) {
      viewBtn.onclick = () => {
        hideProgressModal();
        switchView("projects");
        refreshProjects();
      };
    }
  }

  refreshProjects();
  showToast("🎉 الفيديو جاهز للنشر!");
}

function onJobFailed(job) {
  stopPolling();
  updateProgress(0, "❌ فشل المونتاج");
  $("modalTitle").textContent = "❌ حدث خطأ أثناء المونتاج";
  const errDesc = job.stageLabel || job.error || "خطأ غير معروف";
  appendLog("\n❌ خطأ: " + errDesc + "\n");
  if ($("modalErrorActions")) {
    $("modalErrorActions").style.display = "flex";
    if ($("btnModalGoAuth")) {
      $("btnModalGoAuth").onclick = () => {
        hideProgressModal();
        switchView("brand");
        renderBrandForm();
        setTimeout(() => $("brandYtAuthCard")?.scrollIntoView({ behavior: "smooth" }), 120);
      };
    }
    if ($("btnModalPickLocal")) {
      $("btnModalPickLocal").onclick = () => {
        hideProgressModal();
        switchView("home");
        if (state.pickVideoFile) state.pickVideoFile();
        else $("fileInput")?.click();
      };
    }
  }
  showToast("❌ فشل المونتاج: " + errDesc);
}

// ── Job Polling ────────────────────────────────────────────────────────────────
function startPolling(jobId) {
  stopPolling();
  let seenLines = 0;

  async function poll() {
    try {
      const job = await api(`/api/jobs/${jobId}`);

      // Append new log lines
      const lines = job.logs || job.log || [];
      if (lines.length > seenLines) {
        lines.slice(seenLines).forEach((l) => appendLog(l));
        seenLines = lines.length;
      }

      // Update progress
      const pct = typeof job.pct === "number" ? job.pct : (typeof job.progress === "number" ? job.progress : estimateProgress(job.stage));
      const stage = job.stageLabel || stageLabel(job.stage);
      updateProgress(pct, stage);

      if (job.status === "done") {
        onJobDone(job);
        return;
      }
      if (job.status === "failed" || job.status === "error") {
        onJobFailed(job);
        return;
      }

      // Keep polling
      state.pollTimer = setTimeout(poll, 1500);
    } catch (err) {
      appendLog("⚠️ خطأ في المتابعة: " + err.message);
      state.pollTimer = setTimeout(poll, 3000);
    }
  }

  poll();
}

function stopPolling() {
  if (state.pollTimer) {
    clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
}

function estimateProgress(stage) {
  const map = {
    queued: 2, downloading: 10, download: 15,
    prep: 20, transcribe: 30, captions: 40,
    edit: 55, render: 70, encode: 85,
    finishing: 95, done: 100,
  };
  return map[stage] || 5;
}

function stageLabel(stage) {
  const map = {
    queued: "في الانتظار...",
    downloading: "⬇️ جاري تحميل الفيديو...",
    download: "⬇️ جاري تحميل الفيديو...",
    prep: "🎚️ معالجة أولية...",
    transcribe: "🎙️ تفريغ الكلام...",
    captions: "📝 توليد الترجمة...",
    edit: "✂️ المونتاج...",
    render: "🎨 تصيير الفيديو...",
    encode: "📦 تشفير الفيديو...",
    finishing: "⚡ اللمسات الأخيرة...",
    done: "✅ اكتمل!",
    failed: "❌ فشل",
    error: "❌ خطأ",
  };
  return map[stage] || (stage || "جاري العمل...");
}

// ── Refresh Projects ───────────────────────────────────────────────────────────
async function refreshProjects() {
  try {
    const { projects } = await api("/api/projects");
    state.projects = projects || [];
    renderProjects();
  } catch (e) { /* ignore */ }
}

// ── Brand Form (Master Settings Hub for 1-Click Auto Editing) ──────────────────
function renderBrandForm() {
  const area = $("brandFormArea");
  if (!area) return;

  const brand = state.brand || {};
  const prof = getBrandProfile(state.activeBrandProfile);
  const defs = brand.defaults || {};
  const assets = state.assets || {};
  const musicList = assets.music || [];
  const logoList = assets.logo || [];
  const lutsList = assets.luts || [];

  const logoOptions = logoList.map((l) =>
    `<option value="${l.name}" ${l.name === prof.logoFile ? "selected" : ""}>${l.name}</option>`
  ).join("");

  const curMusic = defs.musicFile !== undefined ? defs.musicFile : (prof.musicFile || "");
  const musicOptions = [
    `<option value="">— بدون موسيقى —</option>`,
    ...musicList.map((m) =>
      `<option value="${m.name}" ${m.name === curMusic ? "selected" : ""}>${m.name}</option>`
    ),
  ].join("");

  const lutOptions = [
    `<option value="">— تلقائي حسب الفلتر —</option>`,
    ...lutsList.map((l) =>
      `<option value="${l.name}" ${l.name === defs.lutFile ? "selected" : ""}>${l.name}</option>`
    ),
  ].join("");

  const glossaryText = (brand.glossary || [])
    .filter((g) => g.wrong && g.right)
    .map((g) => `${g.wrong} -> ${g.right}`)
    .join("\n");

  // Brand switcher within brand view
  const profiles = brand.profiles || [];
  const switcherHtml = profiles.length > 1 ? `
    <div class="brand-switcher-bar" style="margin-bottom:4px;" id="brandViewSwitcher">
      <span class="label-sm">اختر الصفحة:</span>
      ${profiles.map((p) => `
        <button type="button" class="brand-sw-btn ${p.id === state.activeBrandProfile ? "active" : ""}" data-profile="${p.id}">
          <span>${p.accountName || p.id}</span>
        </button>`).join("")}
    </div>` : "";

  area.innerHTML = `
    ${switcherHtml}

    <!-- Card 1: Page Identity & Fixed Texts -->
    <div class="brand-master-card">
      <div class="brand-section-title">1. هوية الصفحة والنصوص الثابتة (البداية والنهاية)</div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">اسم الحساب / العلامة</label>
          <input type="text" class="form-input" id="bAccountName" value="${prof.accountName || ""}" placeholder="غناوي هلنا" />
        </div>
        <div class="form-group">
          <label class="form-label">اللوجو</label>
          <select class="form-input" id="bLogo">${logoOptions || '<option value="">لا توجد ملفات لوجو</option>'}</select>
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">شارة بداية الفيديو (أول 3 ثواني)</label>
          <input type="text" class="form-input" id="bTeaserBadge" value="${defs.teaserBadge || "شاهد للنهاية 🔥"}" placeholder="شاهد للنهاية 🔥" />
        </div>
        <div class="form-group">
          <label class="form-label">جملة نهاية الفيديو (CTA)</label>
          <input type="text" class="form-input" id="bCta" value="${prof.cta || brand.cta || "تابعني ومش هتندم"}" placeholder="تابعني ومش هتندم" />
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">التخصص / المجال</label>
          <input type="text" class="form-input" id="bNiche" value="${prof.niche || brand.niche || ""}" placeholder="غناوي وشعر / تاريخ..." />
        </div>
        <div class="form-group">
          <label class="form-label">الهاشتاجات الافتراضية (في post.txt)</label>
          <input type="text" class="form-input" id="bHashtags" value="${prof.hashtags || brand.hashtags || ""}" />
        </div>
      </div>
      <div class="form-group" style="margin-top:10px; margin-bottom:0;">
        <label class="ed-toggle">
          <input type="checkbox" id="bSalawatOutro" ${defs.salawatOutro ? "checked" : ""} />
          <span>🌙 تفعيل خاتمة «إذا وصلت لنهاية الفيديو صلِّ على النبي ﷺ» افتراضياً بدل جملة النهاية</span>
        </label>
      </div>
    </div>

    <!-- Card 2: Auto Render, Framing & Teaser Hook Defaults -->
    <div class="brand-master-card">
      <div class="brand-section-title">2. إعدادات الرندر والكادر والهوك التلقائي</div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">جودة وسرعة الرندر</label>
          <select class="form-input" id="bRenderQuality">
            <option value="draft" ${defs.renderQuality === "draft" ? "selected" : ""}>فائق السرعة (draft)</option>
            <option value="standard" ${(defs.renderQuality || "standard") === "standard" ? "selected" : ""}>متوازن وسريع (standard — موصى به)</option>
            <option value="looks" ${defs.renderQuality === "looks" ? "selected" : ""}>أعلى جودة (looks — أبطأ)</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">ستايل المونتاج والحركات</label>
          <select class="form-input" id="bStyleMode">
            <option value="fast_hook" ${(defs.styleMode || "fast_hook") === "fast_hook" ? "selected" : ""}>⚡ سريع وحماسي (زوم وحركات)</option>
            <option value="educational" ${defs.styleMode === "educational" ? "selected" : ""}>🎓 تعليمي منظّم</option>
            <option value="storytelling" ${defs.styleMode === "storytelling" ? "selected" : ""}>🎬 قصصي سينمائي هادي</option>
          </select>
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">تصحيح الألوان الافتراضي</label>
          <select class="form-input" id="bColorPreset">
            <option value="warm_creator" ${(defs.colorPreset || "warm_creator") === "warm_creator" ? "selected" : ""}>دافي حيوي (Warm Creator)</option>
            <option value="natural" ${defs.colorPreset === "natural" ? "selected" : ""}>طبيعي نقي (Natural)</option>
            <option value="crisp_edu" ${defs.colorPreset === "crisp_edu" ? "selected" : ""}>تعليمي واضح (Crisp)</option>
            <option value="cinematic" ${defs.colorPreset === "cinematic" ? "selected" : ""}>سينمائي (Cinematic)</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">مقاس الكادر (9:16)</label>
          <select class="form-input" id="bFitMode">
            <option value="cover" ${(defs.fitMode || "cover") === "cover" ? "selected" : ""}>📱 ملء الشاشة (Cover 9:16)</option>
            <option value="blur_bg" ${defs.fitMode === "blur_bg" ? "selected" : ""}>🎬 إطار كامل بخلفية مموهة</option>
          </select>
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">مدة هوك البداية (Teaser)</label>
          <select class="form-input ltr" id="bTeaserDuration">
            <option value="2.5" ${Number(defs.teaserDuration) === 2.5 ? "selected" : ""}>2.5s</option>
            <option value="3" ${(defs.teaserDuration ?? 3) == 3 ? "selected" : ""}>3.0s</option>
            <option value="3.5" ${Number(defs.teaserDuration) === 3.5 ? "selected" : ""}>3.5s</option>
            <option value="4" ${Number(defs.teaserDuration) === 4 ? "selected" : ""}>4.0s</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">ملف LUT (.cube) مخصص</label>
          <select class="form-input" id="bLutFile">${lutOptions}</select>
        </div>
      </div>
      <div class="form-row">
        <label class="ed-toggle">
          <input type="checkbox" id="bTeaserHookEnabled" ${defs.teaserHookEnabled !== false ? "checked" : ""} />
          <span>🔥 تفعيل هوك الـ 3 ثواني تلقائياً في بداية كل فيديو</span>
        </label>
        <label class="ed-toggle">
          <input type="checkbox" id="bShowHookCard" ${defs.showHookCard !== false ? "checked" : ""} />
          <span>🏷️ إظهار كارت العنوان أعلى بداية الفيديو</span>
        </label>
      </div>
      <div class="form-group" style="margin-top:10px; margin-bottom:0;">
        <label class="ed-toggle">
          <input type="checkbox" id="bAutoSmartCrop" ${defs.autoSmartCrop !== false ? "checked" : ""} />
          <span>🤖 قصّ ذكي تلقائي للشرائط الثابتة والكتابات العلوية/السفلية (في الرندر التلقائي)</span>
        </label>
      </div>
    </div>

    <!-- Card 3: Captions, Whisper & Auto Silence Cuts -->
    <div class="brand-master-card">
      <div class="brand-section-title">3. الترجمة التلقائية وقصّ السكوت (Whisper)</div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">شكل الترجمة على الفيديو</label>
          <select class="form-input" id="bCaptionStyle">
            <option value="karaoke" ${(defs.captionStyle || "karaoke") === "karaoke" ? "selected" : ""}>Karaoke كلمة بكلمة</option>
            <option value="chunk_highlight" ${defs.captionStyle === "chunk_highlight" ? "selected" : ""}>مقاطع + تلوين الكلمة</option>
            <option value="word_by_word" ${defs.captionStyle === "word_by_word" ? "selected" : ""}>كلمة منفصلة</option>
            <option value="box_bg" ${defs.captionStyle === "box_bg" ? "selected" : ""}>صندوق بخط جانبي</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">أقصى كلمات بالسطر: <span id="bMaxWordsVal">${defs.maxWords ?? 4}</span></label>
          <input type="range" min="2" max="6" step="1" id="bMaxWords" value="${defs.maxWords ?? 4}" />
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">موديل Whisper للتفريغ</label>
          <select class="form-input" id="bWhisperModel">
            <option value="small" ${(defs.whisperModel || "small") === "small" ? "selected" : ""}>small (سريع ومتوازن)</option>
            <option value="medium" ${defs.whisperModel === "medium" ? "selected" : ""}>medium (دقة أعلى — أبطأ)</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">قصّ السكوت الأطول من: <span class="ltr" id="bMinSilenceVal">${defs.minSilence ?? 0.4}s</span></label>
          <input type="range" min="0.25" max="1.0" step="0.05" id="bMinSilence" value="${defs.minSilence ?? 0.4}" />
        </div>
      </div>
      <div class="form-row">
        <label class="ed-toggle">
          <input type="checkbox" id="bWhisperEnabled" ${defs.whisperEnabled !== false ? "checked" : ""} />
          <span>🗣️ تفعيل تفريغ الكلام والترجمة تلقائياً</span>
        </label>
        <label class="ed-toggle">
          <input type="checkbox" id="bAutoCutSilences" ${defs.autoCutSilences !== false ? "checked" : ""} />
          <span>✂️ قصّ لحظات السكوت تلقائياً</span>
        </label>
      </div>
      <div class="form-group" style="margin-top:10px; margin-bottom:0;">
        <label class="ed-toggle">
          <input type="checkbox" id="bBilingualCaptions" ${defs.bilingualCaptions !== false ? "checked" : ""} />
          <span>🌐 ترجمة ثنائية اللغة (العربي بالأعلى + الإنجليزي تحته بخط أصغر)</span>
        </label>
      </div>
    </div>

    <!-- Card 4: Audio, Music, SFX & Colors -->
    <div class="brand-master-card">
      <div class="brand-section-title">4. الصوت والمؤثرات والألوان والقاموس</div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">الموسيقى الخلفية الافتراضية</label>
          <select class="form-input" id="bMusic">${musicOptions}</select>
        </div>
        <div class="form-group">
          <label class="form-label">مستوى الموسيقى: <span class="ltr" id="bMusicDbVal">${defs.musicDb ?? -23} dB</span></label>
          <input type="range" min="-34" max="-14" step="1" id="bMusicDb" value="${defs.musicDb ?? -23}" />
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">فلتر معالجة الصوت الافتراضي</label>
          <select class="form-input" id="bVoicePreset">
            <option value="studio" ${(defs.voicePreset || "studio") === "studio" ? "selected" : ""}>استوديو نقي (Studio)</option>
            <option value="podcast" ${defs.voicePreset === "podcast" ? "selected" : ""}>بودكاست عميق (Podcast)</option>
            <option value="heritage_reverb" ${defs.voicePreset === "heritage_reverb" ? "selected" : ""}>صدى تراثي خفيف (Reverb)</option>
            <option value="cinema" ${defs.voicePreset === "cinema" ? "selected" : ""}>سينمائي دافي (Cinema)</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">وضوح أصوات مؤثرات الشوت (SFX): <span class="ltr" id="bSfxDbVal">${defs.sfxDb ?? -5} dB</span></label>
          <input type="range" min="-14" max="0" step="1" id="bSfxDb" value="${defs.sfxDb ?? -5}" />
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">إزالة الضوضاء (Denoise)</label>
          <select class="form-input" id="bDenoise">
            <option value="light" ${(defs.denoise || "light") === "light" ? "selected" : ""}>خفيف</option>
            <option value="medium" ${defs.denoise === "medium" ? "selected" : ""}>متوسط</option>
            <option value="strong" ${defs.denoise === "strong" ? "selected" : ""}>قوي</option>
            <option value="off" ${defs.denoise === "off" ? "selected" : ""}>مغلق</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">لون التمييز Accent (HEX)</label>
          <div class="ed-color-row">
            <input type="color" id="bAccentColorPicker" value="${prof.colors?.accent || "#F5C542"}" />
            <input type="text" class="form-input ltr" id="bAccentColor" value="${prof.colors?.accent || "#F5C542"}" style="flex:1; padding:4px 8px;" />
          </div>
        </div>
      </div>
      <div class="form-row" style="margin-bottom:14px;">
        <label class="ed-toggle">
          <input type="checkbox" id="bAutoDuck" ${defs.autoDuck !== false ? "checked" : ""} />
          <span>🔉 توطية الموسيقى تلقائياً وقت الكلام (Auto-Duck)</span>
        </label>
        <label class="ed-toggle">
          <input type="checkbox" id="bSfxEnabled" ${defs.sfxEnabled !== false ? "checked" : ""} />
          <span>🔊 تفعيل أصوات مؤثرات الشوت والانتقالات (SFX)</span>
        </label>
      </div>
      <div class="form-group" style="margin-bottom:0;">
        <label class="form-label">قاموس تصحيح الكلمات التلقائي (صيغة: الخطأ -> الصواب، كل قاعدة في سطر)</label>
        <textarea class="form-input brand-glossary-input" id="bGlossary">${glossaryText}</textarea>
      </div>
    </div>

    <!-- Card 5: Official YouTube Authentication (Cookies File OR User-Selected Browser) -->
    <div class="brand-master-card" id="brandYtAuthCard">
      <div class="brand-section-title">5. مصادقة روابط يوتيوب (حل دائم لمشكلة التحميل)</div>
      <p class="ed-hint" style="margin-top:0; margin-bottom:10px;">
        لما يوتيوب يطلب تسجيل الدخول (<code>Sign in to confirm you're not a bot</code>)، اختر طريقة المصادقة الرسمية بحسابك:
        <strong>Firefox</strong> يعمل تلقائياً بدون إضافات (لو مسجّل دخولك فيه على يوتيوب)، أو ارفع ملف <span class="ltr">cookies.txt</span> مرة واحدة.
      </p>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">طريقة مصادقة يوتيوب الرسمية</label>
          <select class="form-input" id="bYtAuthMode">
            <option value="auto" ${(defs.ytAuthMode || "auto") === "auto" ? "selected" : ""}>تلقائي (يستخدم cookies.txt إن وُجد)</option>
            <option value="firefox" ${defs.ytAuthMode === "firefox" ? "selected" : ""}>🦊 من متصفح Firefox (تلقائي ودائم — موصى به)</option>
            <option value="cookies_file" ${defs.ytAuthMode === "cookies_file" ? "selected" : ""}>🍪 من ملف cookies.txt المرفوع</option>
            <option value="edge" ${defs.ytAuthMode === "edge" ? "selected" : ""}>🌐 من متصفح Microsoft Edge</option>
            <option value="chrome" ${defs.ytAuthMode === "chrome" ? "selected" : ""}>🌐 من متصفح Google Chrome</option>
            <option value="brave" ${defs.ytAuthMode === "brave" ? "selected" : ""}>🦁 من متصفح Brave</option>
            <option value="none" ${defs.ytAuthMode === "none" ? "selected" : ""}>بدون مصادقة</option>
          </select>
        </div>
        <div class="form-group" style="justify-content:flex-end;">
          <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
            <input type="file" id="bCookiesInput" accept=".txt" hidden />
            <button type="button" class="btn btn-sm" id="btnUploadCookies">🍪 رفع ملف cookies.txt</button>
            <button type="button" class="btn btn-danger btn-sm" id="btnDeleteCookies" style="display:${state.status?.ytCookies?.ok ? "inline-flex" : "none"};">🗑️ حذف</button>
            <span id="bCookiesStatus" style="font-size:12px; color:${state.status?.ytCookies?.ok ? "var(--green, #22c55e)" : "var(--text-dim)"};">
              ${state.status?.ytCookies?.ok ? "✅ cookies.txt مفعّل" : "غير مرفوع"}
            </span>
          </div>
        </div>
      </div>
      <div class="form-row" style="margin-top:8px;">
        <div class="form-group">
          <label class="form-label">💾 فولدر الحفظ المباشر للفيديوهات الجاهزة</label>
          <input type="text" class="form-input ltr" id="bExportFolder" value="${defs.exportFolder || "D:\\غناوي هلنا"}" placeholder="D:\\غناوي هلنا" />
        </div>
        <div class="form-group">
          <label class="form-label">📂 فولدر متابعة إضافي في رادار التحميلات (بجانب Downloads)</label>
          <input type="text" class="form-input ltr" id="bWatchFolder" value="${defs.watchFolder || ""}" placeholder="مثال: D:\\غناوي هلنا" />
        </div>
      </div>
      <div class="form-group" style="margin-bottom:0;">
        <button type="button" class="btn btn-sm" id="btnUpdateYtdlp">🔄 تحديث محرك الروابط (yt-dlp)</button>
      </div>
    </div>

    <button type="button" class="btn-save-brand" id="btnSaveBrand">💾 حفظ كل إعدادات الهوية والرندر (تُطبق تلقائياً على كل فيديو جديد)</button>
  `;

  // Live range readouts & color sync
  $("bMaxWords")?.addEventListener("input", (e) => { $("bMaxWordsVal").textContent = e.target.value; });
  $("bMinSilence")?.addEventListener("input", (e) => { $("bMinSilenceVal").textContent = `${e.target.value}s`; });
  $("bMusicDb")?.addEventListener("input", (e) => { $("bMusicDbVal").textContent = `${e.target.value} dB`; });
  $("bSfxDb")?.addEventListener("input", (e) => { $("bSfxDbVal").textContent = `${e.target.value} dB`; });
  $("bAccentColorPicker")?.addEventListener("input", (e) => { $("bAccentColor").value = e.target.value; });
  $("bAccentColor")?.addEventListener("input", (e) => {
    if (/^#[0-9A-Fa-f]{6}$/.test(e.target.value)) $("bAccentColorPicker").value = e.target.value;
  });

  // Brand view switcher
  area.querySelectorAll("#brandViewSwitcher .brand-sw-btn[data-profile]").forEach((btn) => {
    btn.addEventListener("click", () => {
      switchBrandProfile(btn.dataset.profile);
      renderBrandForm();
    });
  });

  // Save brand
  $("btnSaveBrand")?.addEventListener("click", saveBrand);

  // YouTube cookies.txt upload / delete
  $("btnUploadCookies")?.addEventListener("click", () => $("bCookiesInput")?.click());
  $("bCookiesInput")?.addEventListener("change", async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    try {
      await api("/api/cookies/upload", { method: "POST", body: f });
      await loadStatus();
      renderBrandForm();
      showToast("✅ تم حفظ ملف cookies.txt لمصادقة روابط يوتيوب!");
    } catch (err) {
      showToast("❌ فشل رفع الكوكيز: " + err.message);
    }
    e.target.value = "";
  });
  $("btnDeleteCookies")?.addEventListener("click", async () => {
    try {
      await api("/api/cookies", { method: "DELETE" });
      await loadStatus();
      renderBrandForm();
      showToast("🗑️ تم حذف ملف الكوكيز");
    } catch (err) {
      showToast("❌ " + err.message);
    }
  });
  $("btnUpdateYtdlp")?.addEventListener("click", async () => {
    const btn = $("btnUpdateYtdlp");
    if (btn) { btn.disabled = true; btn.textContent = "⏳ جاري التحديث..."; }
    try {
      const res = await api("/api/tools/update-ytdlp", { method: "POST" });
      showToast(`✅ تم تحديث محرك الروابط (yt-dlp ${res.version || ""})`);
      await loadStatus();
    } catch (err) {
      showToast("❌ " + err.message);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = "🔄 تحديث محرك الروابط (yt-dlp)"; }
    }
  });
}

async function saveBrand() {
  const prof = getBrandProfile(state.activeBrandProfile);
  const curBrand = state.brand || {};
  const glossaryLines = ($("bGlossary")?.value || "").split(/\r?\n/);
  const glossary = glossaryLines
    .map((line) => line.split("->"))
    .filter((parts) => parts.length === 2 && parts[0].trim() && parts[1].trim())
    .map(([wrong, right]) => ({ wrong: wrong.trim(), right: right.trim() }));

  const chosenAccent = $("bAccentColor")?.value.trim() || prof.colors?.accent || "#F5C542";
  const ctaVal = $("bCta")?.value.trim() || "تابعني ومش هتندم";
  const hashtagsVal = $("bHashtags")?.value.trim() || prof.hashtags || curBrand.hashtags || "";

  const profiles = (curBrand.profiles || []).map((p) => {
    if (p && p.id === state.activeBrandProfile) {
      return {
        ...p,
        accountName: $("bAccountName")?.value.trim() || p.accountName,
        niche: $("bNiche")?.value.trim() || "",
        cta: ctaVal,
        logoFile: $("bLogo")?.value || p.logoFile,
        hashtags: hashtagsVal,
        colors: { ...(p.colors || {}), accent: chosenAccent },
      };
    }
    return p;
  });

  const payload = {
    editingProfileId: state.activeBrandProfile,
    accountName: $("bAccountName")?.value.trim() || prof.accountName,
    cta: ctaVal,
    logoFile: $("bLogo")?.value || prof.logoFile,
    niche: $("bNiche")?.value.trim() || "",
    hashtags: hashtagsVal,
    colors: {
      ...(prof.colors || {}),
      accent: chosenAccent,
    },
    profiles,
    glossary,
    defaults: {
      ...(curBrand.defaults || {}),
      renderQuality: $("bRenderQuality")?.value || "standard",
      styleMode: $("bStyleMode")?.value || "fast_hook",
      colorPreset: $("bColorPreset")?.value || "warm_creator",
      fitMode: $("bFitMode")?.value || "cover",
      autoSmartCrop: Boolean($("bAutoSmartCrop")?.checked),
      lutFile: $("bLutFile")?.value || "",
      teaserHookEnabled: Boolean($("bTeaserHookEnabled")?.checked),
      teaserDuration: Number($("bTeaserDuration")?.value || 3),
      teaserBadge: $("bTeaserBadge")?.value.trim() || "شاهد للنهاية 🔥",
      showHookCard: Boolean($("bShowHookCard")?.checked),
      salawatOutro: Boolean($("bSalawatOutro")?.checked),
      ytAuthMode: $("bYtAuthMode")?.value || "auto",
      exportFolder: $("bExportFolder")?.value.trim() || "D:\\غناوي هلنا",
      watchFolder: $("bWatchFolder")?.value.trim() || "",
      captionStyle: $("bCaptionStyle")?.value || "karaoke",
      bilingualCaptions: Boolean($("bBilingualCaptions")?.checked),
      maxWords: Number($("bMaxWords")?.value || 4),
      whisperModel: $("bWhisperModel")?.value || "small",
      whisperEnabled: Boolean($("bWhisperEnabled")?.checked),
      autoCutSilences: Boolean($("bAutoCutSilences")?.checked),
      minSilence: Number($("bMinSilence")?.value || 0.4),
      musicFile: $("bMusic")?.value ?? "",
      musicDb: Number($("bMusicDb")?.value ?? -23),
      autoDuck: Boolean($("bAutoDuck")?.checked),
      sfxEnabled: Boolean($("bSfxEnabled")?.checked),
      sfxDb: Number($("bSfxDb")?.value ?? -5),
      voicePreset: $("bVoicePreset")?.value || "studio",
      denoise: $("bDenoise")?.value || "light",
    },
  };

  try {
    const { brand } = await api("/api/brand", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.brand = brand;
    applyTheme();
    showToast("✅ تم حفظ الهوية بنجاح!");
  } catch (err) {
    showToast("❌ " + err.message);
  }
}

// ── Initialization ─────────────────────────────────────────────────────────────
async function init() {
  // Wire nav items
  document.querySelectorAll(".nav-item[data-view]").forEach((btn) => {
    btn.addEventListener("click", () => {
      switchView(btn.dataset.view);
      if (btn.dataset.view === "projects") refreshProjects();
      if (btn.dataset.view === "brand") renderBrandForm();
    });
  });

  // Brand switcher buttons in home view
  document.querySelectorAll("#homeBrandSwitcher .brand-sw-btn[data-profile]").forEach((btn) => {
    btn.addEventListener("click", () => switchBrandProfile(btn.dataset.profile));
  });

  // Go home from projects
  $("btnGoHome")?.addEventListener("click", () => switchView("home"));

  // Refresh button
  $("btnRefreshAll")?.addEventListener("click", async () => {
    showToast("🔄 جاري التحديث...");
    await Promise.all([loadBrand(), refreshProjects(), loadStatus()]);
    renderBrandForm();
    showToast("✅ تم التحديث");
  });

  // Open folder
  $("btnOpenRootFolder")?.addEventListener("click", () => {
    api("/api/open-folder", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) })
      .catch(() => {});
  });

  // Modal close
  $("btnModalClose")?.addEventListener("click", hideProgressModal);
  $("progressModal")?.addEventListener("click", (e) => {
    if (e.target === $("progressModal")) hideProgressModal();
  });

  // Setup home view & post-processing editor
  setupHomeView();
  setupEditor();

  // Load data
  await Promise.all([loadBrand(), refreshProjects(), loadStatus(), loadRecentDownloads(false)]);

  applyTheme();
  renderProjects();
  renderHealth();
  renderBrandForm();
}

async function loadBrand() {
  try {
    const [brand, assets] = await Promise.all([api("/api/brand"), api("/api/assets")]);
    state.brand = brand;
    state.assets = assets;
    if (brand.defaultProfileId) state.activeBrandProfile = brand.defaultProfileId;
  } catch (e) { /* use defaults */ }
}

async function loadStatus() {
  try {
    state.status = await api("/api/status");
    renderHealth();
  } catch (e) { /* ignore */ }
}

const FONT_CSS_MAP = {
  cairo: "CairoStudio",
  tajawal: "TajawalStudio",
  amiri: "AmiriStudio",
  changa: "ChangaStudio",
  reemkufi: "ReemKufiStudio",
};

function switchEditorTab(tabName) {
  state.editor.activeTab = tabName;
  document.querySelectorAll("#editorControlTabs .ed-tab-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.edTab === tabName);
  });
  document.querySelectorAll(".ed-tab-panel").forEach((p) => {
    p.classList.toggle("active", p.id === `edPanel-${tabName}`);
  });
  // Crop tab -> always show raw video with 4-edge crop box
  if (tabName === "crop" && state.editor.project?.files?.inputUrl) {
    setEditorPreviewSource("raw");
  } else if (tabName === "text" && state.editor.previewMode === "output") {
    // When editing text, switch off baked output.mp4 so HTML boxes never duplicate over rendered video!
    if (state.editor.cropPreviewUrl) setEditorPreviewSource("cropped");
    else if (state.editor.project?.files?.inputUrl) setEditorPreviewSource("raw");
  } else {
    updateEditorCropPreview();
  }
}

function setEditorPreviewSource(srcMode) {
  const proj = state.editor.project;
  if (!proj) return;
  const hasOut = Boolean(proj.files?.outputUrl);
  const hasCropped = Boolean(state.editor.cropPreviewUrl);
  let chosen = "raw";
  if (srcMode === "output" && hasOut) chosen = "output";
  else if (srcMode === "cropped" && hasCropped) chosen = "cropped";
  state.editor.previewMode = chosen;

  document.querySelectorAll("#edPreviewSrcBar .guide-pill").forEach((p) => {
    p.classList.toggle("active", p.dataset.previewSrc === chosen);
  });
  const outBtn = $("btnPreviewOutput");
  if (outBtn) outBtn.style.display = hasOut ? "inline-flex" : "none";
  const cropBtn = $("btnPreviewCropped");
  if (cropBtn) cropBtn.style.display = hasCropped ? "inline-flex" : "none";

  // CRITICAL: Hide HTML overlay canvas when viewing final rendered output.mp4 so text NEVER appears duplicated!
  const ovCanvas = $("edOverlayCanvas");
  if (ovCanvas) ovCanvas.style.display = chosen === "output" ? "none" : "block";

  const vid = $("edVideoPlayer");
  const url =
    chosen === "output"
      ? proj.files.outputUrl
      : (chosen === "cropped" ? state.editor.cropPreviewUrl : (proj.files?.inputUrl || proj.files?.outputUrl));
  if (vid && url) {
    const curTime = vid.currentTime || 0;
    const baseUrl = url.split("?")[0];
    const targetSrc = url.includes("?t=") ? url : `${url}?t=${Date.now()}`;
    if (!vid.src || !vid.src.includes(baseUrl) || url.includes("?t=")) {
      vid.src = targetSrc;
      vid.addEventListener("loadedmetadata", () => {
        if (curTime > 0 && curTime < (vid.duration || 999)) vid.currentTime = curTime;
        updateEditorCropPreview();
        renderEditorTimeline();
      }, { once: true });
    }
  }
  updateEditorCropPreview();
}

// ── Post-Processing Editor (Add Text / Hide & Replace Existing Text) ───────────
async function openEditor(projectId) {
  try {
    const { project } = await api(`/api/projects/${encodeURIComponent(projectId)}`);
    const s = project.settings || {};
    state.editor.project = project;
    state.editor.overlays = (Array.isArray(s.overlays) ? s.overlays : []).map((o, idx) => ({
      id: o.id || `ov-${Date.now()}-${idx}`,
      mode: o.mode || "replace",
      x: Number(o.x ?? 6),
      y: Number(o.y ?? 74),
      w: Number(o.w ?? 88),
      h: Number(o.h ?? 12),
      text: o.text || "",
      cardStyle: o.cardStyle || "solid_dark",
      fontFamily: o.fontFamily || s.arabicFont || "cairo",
      fontSize: Number(o.fontSize || 46),
      textColor: o.textColor || "#FFFFFF",
      mediaFile: o.mediaFile || "",
      start: Number(o.start || 0),
      end: Number(o.end || 0),
    }));
    state.editor.selectedId = state.editor.overlays[0]?.id || null;
    state.editor.drawMode = false;
    // Start with a 100% CLEAN video screen — guides only show when user clicks a toggle pill
    state.editor.visibleGuides = { wm: false, hook: false, cap: false, cta: false };
    document.querySelectorAll("#edGuideToggleBar .guide-pill").forEach((p) => p.classList.remove("active"));

    state.editor.hookY = s.hookY !== undefined && s.hookY !== null && s.hookY !== "" ? Number(s.hookY) : null;
    state.editor.captionsY = s.captionsY !== undefined && s.captionsY !== null && s.captionsY !== "" ? Number(s.captionsY) : null;
    state.editor.ctaY = s.ctaY !== undefined && s.ctaY !== null && s.ctaY !== "" ? Number(s.ctaY) : null;
    state.editor.watermarkX = s.watermarkX !== undefined && s.watermarkX !== null && s.watermarkX !== "" ? Number(s.watermarkX) : null;
    state.editor.watermarkY = s.watermarkY !== undefined && s.watermarkY !== null && s.watermarkY !== "" ? Number(s.watermarkY) : null;
    state.editor.showWatermark = s.showWatermark !== false;

    $("editorProjectTitle").textContent = s.title || project.id;
    $("edHookTitle").value = s.hookTitle || "";
    $("edCtaText").value = s.ctaText || "";
    $("edShowHookCard").checked = s.showHookCard !== false;
    if ($("edShowCaptions")) $("edShowCaptions").checked = s.showCaptions !== false;
    if ($("edSalawatOutro")) $("edSalawatOutro").checked = Boolean(s.salawatOutro);
    if ($("edArabicFont")) $("edArabicFont").value = s.arabicFont || "cairo";

    // Crop, Zoom, Trim & Middle Cut Segments (live pre-render editing)
    state.editor.cutSegments = Array.isArray(s.cutSegments) ? s.cutSegments.map((x) => ({ ...x })) : [];
    renderEditorCutSegments();
    if ($("edFitMode")) $("edFitMode").value = s.fitMode || "cover";
    if ($("edCropZoom")) $("edCropZoom").value = Number(s.cropZoom || 1);
    if ($("edCropPanX")) $("edCropPanX").value = Number(s.cropPanX || 0);
    if ($("edCropPanY")) $("edCropPanY").value = Number(s.cropPanY || 0);
    if ($("edCropTop")) $("edCropTop").value = Number(s.cropTop || 0);
    if ($("edCropBottom")) $("edCropBottom").value = Number(s.cropBottom || 0);
    if ($("edCropLeft")) $("edCropLeft").value = Number(s.cropLeft || 0);
    if ($("edCropRight")) $("edCropRight").value = Number(s.cropRight || 0);
    if ($("edTrimStart")) $("edTrimStart").value = Number(s.trimStart || 0);
    if ($("edTrimEnd")) $("edTrimEnd").value = Number(s.trimEnd || 0);
    state.editor.tlCutMode = false;
    $("btnTlCutMode")?.classList.remove("active");
    $("edTimelineBar")?.classList.remove("cut-mode");

    // Dynamic primary render button label (Raw = Full Render, Rendered = Apply Edits)
    const isRaw = !project.files?.hasOutput && !project.files?.hasCut;
    if ($("btnEditorRerender")) {
      $("btnEditorRerender").textContent = isRaw
        ? "🚀 موافق — ابدأ المونتاج والرندر النهائي"
        : "⚡ تطبيق التعديلات (رندر سريع)";
    }

    // Audio & Voice FX fields
    state.editor.audioSource = s.audioSource || "original";
    state.editor.customSfx = Array.isArray(s.customSfx) ? s.customSfx.map((x) => ({ ...x })) : [];
    $("edVoicePreset").value = s.voicePreset || "studio";
    $("edDenoise").value = s.denoise || "light";
    $("edMuteOriginal").checked = Boolean(s.muteOriginal);
    $("edTtsText").value = s.ttsText || "";
    $("edTtsVoice").value = s.ttsVoice || "salma";
    $("edTtsRate").value = s.ttsRate || "+0%";
    $("edVoiceFileStatus").textContent = s.customVoiceName ? `✅ ${s.customVoiceName}` : "لم يتم رفع صوت بعد";
    if ($("edCustomVoicePreview")) $("edCustomVoicePreview").style.display = "none";
    if ($("edTtsPreview")) $("edTtsPreview").style.display = "none";
    syncAudioSourceTabs();
    renderEditorSfx();

    // Default tab: Crop if raw video, Text if already rendered; load existing crop preview if present
    state.editor.cropPreviewUrl = project.files?.cropPreviewUrl || null;
    switchEditorTab(isRaw ? "crop" : "text");
    setEditorPreviewSource(isRaw ? "raw" : (state.editor.cropPreviewUrl ? "cropped" : "output"));

    updateDrawModeBtn();
    renderEditorOverlays();
    renderOverlayInspector();
    switchView("editor");
  } catch (err) {
    showToast("❌ تعذّر فتح المحرر: " + err.message);
  }
}

function updateDrawModeBtn() {
  const btn = $("btnDrawOverlay");
  const canvas = $("edOverlayCanvas");
  if (btn) {
    btn.textContent = state.editor.drawMode ? "✖️ إلغاء الرسم" : "✏️ رسم مربع على الفيديو";
    btn.classList.toggle("btn-danger", state.editor.drawMode);
    btn.classList.toggle("btn-accent", !state.editor.drawMode);
  }
  if (canvas) {
    canvas.classList.toggle("draw-mode", state.editor.drawMode);
  }
}

function addOverlayPreset(preset) {
  const id = `ov-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
  const item = {
    id,
    mode: "replace",
    x: 6,
    y: 74,
    w: 88,
    h: 12,
    text: "",
    cardStyle: "solid_dark",
    fontSize: 46,
    textColor: "#FFFFFF",
    start: 0,
    end: 0,
    ...preset,
  };
  state.editor.overlays.push(item);
  state.editor.selectedId = id;
  state.editor.drawMode = false;
  updateDrawModeBtn();
  renderEditorOverlays();
  renderOverlayInspector();
}

function getSelectedOverlay() {
  return state.editor.overlays.find((o) => o.id === state.editor.selectedId) || null;
}

function renderEditorOverlays() {
  const list = $("edOverlaysList");
  const canvas = $("edOverlayCanvas");
  const listHtml = state.editor.overlays.map((o, idx) => {
    const modeIcon = o.mode === "delogo" ? "🧹" : (o.mode === "blur" ? "🌫️" : (o.mode === "image" ? "🖼️" : (o.mode === "video" ? "🎞️" : "📝")));
    const label = o.text
      ? o.text.slice(0, 18)
      : (o.mediaFile ? o.mediaFile.slice(0, 16) : (o.mode === "delogo" ? "مسح لوجو" : (o.mode === "blur" ? "تغبيش" : `عنصر ${idx + 1}`)));
    const active = o.id === state.editor.selectedId ? "active" : "";
    return `<button type="button" class="ov-chip ${active}" data-ov-id="${o.id}">${modeIcon} ${label}</button>`;
  }).join("");
  if (list) {
    list.innerHTML = listHtml || `<span class="ed-hint" style="margin:0;">لا توجد نصوص أو صور/فيديوهات مضافة بعد.</span>`;
    list.querySelectorAll(".ov-chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.editor.selectedId = btn.dataset.ovId;
        renderEditorOverlays();
        renderOverlayInspector();
      });
    });
  }

  if (canvas) {
    const projId = state.editor.project?.id;
    const vg = state.editor.visibleGuides || {};
    const hookY = state.editor.hookY !== null && state.editor.hookY !== undefined ? state.editor.hookY : 13;
    const capY = state.editor.captionsY !== null && state.editor.captionsY !== undefined ? state.editor.captionsY : 72;
    const ctaY = state.editor.ctaY !== null && state.editor.ctaY !== undefined ? state.editor.ctaY : 83;
    const wmX = state.editor.watermarkX;
    const wmY = state.editor.watermarkY !== null && state.editor.watermarkY !== undefined ? state.editor.watermarkY : 4;
    const showHook = $("edShowHookCard")?.checked !== false;
    const showWm = state.editor.showWatermark !== false;
    const hookTxt = $("edHookTitle")?.value.trim() || "عنوان الهوك (دبل كليك للتعديل)";
    const salawatOn = Boolean($("edSalawatOutro")?.checked);
    const ctaTxt = salawatOn
      ? "🌙 إذا وصلت لنهاية الفيديو صلِّ على النبي ﷺ"
      : ($("edCtaText")?.value.trim() || "تابعني ومش هتندم");
    const wmStyle = wmX !== null && wmX !== undefined ? `left:${wmX}%; top:${wmY}%; right:auto;` : `top:${wmY}%;`;
    const globalFontCss = FONT_CSS_MAP[$("edArabicFont")?.value || "cairo"] || "CairoStudio";

    // Only render guide boxes that the user explicitly toggled ON (keeps canvas 100% clean!)
    const guidesHtml = `
      ${vg.wm ? `<div class="ed-guide-box wm-guide ${showWm ? "" : "is-hidden-el"}" id="edWatermarkGuide" style="${wmStyle}" title="اسحب اللوجو لأي مكان">
        <span>🏷️ اللوجو</span>
        <button type="button" class="ed-guide-eye" id="btnEdToggleWm" title="إظهار / إخفاء اللوجو">${showWm ? "👁️" : "🚫"}</button>
      </div>` : ""}
      ${vg.hook ? `<div class="ed-guide-box ${showHook ? "" : "is-hidden-el"}" id="edHookGuide" style="top:${hookY}%; font-family:${globalFontCss}, sans-serif;" title="اسحب لتحريكه · دبل كليك لتعديل النص مباشرة">
        <span class="ed-guide-tag">↕️ العنوان (دبل كليك للتعديل) <button type="button" class="ed-guide-eye" id="btnEdToggleHook">${showHook ? "👁️" : "🚫"}</button></span>
        <span id="edHookGuideText">${hookTxt.slice(0, 42)}</span>
      </div>` : ""}
      ${vg.cap ? `<div class="ed-guide-box captions-guide" id="edCaptionsGuide" style="top:${capY}%; font-family:${globalFontCss}, sans-serif;" title="اسحب لتحريك مكان الترجمة">
        <span class="ed-guide-tag">↕️ مكان الترجمة (اسحب)</span>
        <span>الترجمة التلقائية</span>
      </div>` : ""}
      ${vg.cta ? `<div class="ed-guide-box cta-guide" id="edCtaGuide" style="top:${ctaY}%; font-family:${globalFontCss}, sans-serif;" title="اسحب لتحريك الخاتمة · دبل كليك لتعديل النص مباشرة">
        <span class="ed-guide-tag">↕️ جملة النهاية (دبل كليك للتعديل)</span>
        <span id="edCtaGuideText">${ctaTxt.slice(0, 42)}</span>
      </div>` : ""}
    `;

    const canvasW = canvas.clientWidth || 330;
    const boxesHtml = state.editor.overlays.map((o) => {
      const sel = o.id === state.editor.selectedId ? "selected" : "";
      const styleCls = o.mode === "replace" ? `style-${o.cardStyle || "solid_dark"}` : "";
      const ovFontCss = FONT_CSS_MAP[o.fontFamily || $("edArabicFont")?.value || "cairo"] || "CairoStudio";
      const previewPx = Math.max(10, Math.round((Number(o.fontSize) || 46) * (canvasW / 1080)));
      let innerHtml = "";
      if (o.mode === "image" && o.mediaFile && projId) {
        const mUrl = o.mediaUrl || `/media/videos/${encodeURIComponent(projId)}/broll/${encodeURIComponent(o.mediaFile)}`;
        innerHtml = `<img src="${mUrl}" class="ov-box-media" alt="" />`;
      } else if (o.mode === "video" && o.mediaFile && projId) {
        const mUrl = o.mediaUrl || `/media/videos/${encodeURIComponent(projId)}/broll/${encodeURIComponent(o.mediaFile)}`;
        innerHtml = `<video src="${mUrl}" class="ov-box-media" muted loop autoplay playsinline></video>`;
      } else {
        const label = o.mode === "replace"
          ? (o.text || "دبل كليك للكتابة")
          : (o.mode === "blur" ? "تغبيش ناعم" : "مسح لوجو");
        const safeLabel = String(label).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        innerHtml = `<span class="ov-box-label" style="font-size:${previewPx}px; font-family:${ovFontCss}, sans-serif;">${safeLabel}</span>`;
      }
      return `
        <div class="ov-box mode-${o.mode} ${styleCls} ${sel}" data-ov-id="${o.id}"
             style="left:${o.x}%; top:${o.y}%; width:${o.w}%; height:${o.h}%; color:${o.textColor || "#FFFFFF"};">
          ${innerHtml}
          <span class="ov-resize-handle" data-resize-id="${o.id}"></span>
        </div>`;
    }).join("");

    canvas.innerHTML = guidesHtml + boxesHtml;

    // Eye toggles directly on video
    $("btnEdToggleWm")?.addEventListener("mousedown", (e) => e.stopPropagation());
    $("btnEdToggleWm")?.addEventListener("click", (e) => {
      e.stopPropagation();
      state.editor.showWatermark = !state.editor.showWatermark;
      renderEditorOverlays();
    });
    $("btnEdToggleHook")?.addEventListener("mousedown", (e) => e.stopPropagation());
    $("btnEdToggleHook")?.addEventListener("click", (e) => {
      e.stopPropagation();
      if ($("edShowHookCard")) $("edShowHookCard").checked = !$("edShowHookCard").checked;
      renderEditorOverlays();
    });

    // Inline text editing directly on the video screen (double-click)
    const startInlineEdit = (containerEl, initialValue, onCommit) => {
      if (!containerEl || containerEl.querySelector("input")) return;
      const inp = document.createElement("input");
      inp.type = "text";
      inp.className = "ed-inline-input";
      inp.value = initialValue;
      inp.addEventListener("mousedown", (ev) => ev.stopPropagation());
      const finish = () => {
        onCommit(inp.value);
        renderEditorOverlays();
      };
      inp.addEventListener("blur", finish);
      inp.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") { ev.preventDefault(); inp.blur(); }
        if (ev.key === "Escape") { inp.value = initialValue; inp.blur(); }
      });
      containerEl.innerHTML = "";
      containerEl.appendChild(inp);
      inp.focus();
      inp.select();
    };

    // Draggable Watermark (X & Y)
    const wmEl = $("edWatermarkGuide");
    if (wmEl) {
      wmEl.addEventListener("mousedown", (e) => {
        if (state.editor.drawMode || e.target.closest("button")) return;
        e.stopPropagation();
        const rect = canvas.getBoundingClientRect();
        const boxRect = wmEl.getBoundingClientRect();
        const startX = e.clientX;
        const startY = e.clientY;
        const origLeftPct = ((boxRect.left - rect.left) / rect.width) * 100;
        const origTopPct = ((boxRect.top - rect.top) / rect.height) * 100;
        const onMove = (ev) => {
          const nx = Math.max(2, Math.min(72, Math.round((origLeftPct + ((ev.clientX - startX) / rect.width) * 100) * 10) / 10));
          const ny = Math.max(2, Math.min(88, Math.round((origTopPct + ((ev.clientY - startY) / rect.height) * 100) * 10) / 10));
          state.editor.watermarkX = nx;
          state.editor.watermarkY = ny;
          wmEl.style.right = "auto";
          wmEl.style.left = `${nx}%`;
          wmEl.style.top = `${ny}%`;
        };
        const onUp = () => {
          window.removeEventListener("mousemove", onMove);
          window.removeEventListener("mouseup", onUp);
        };
        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
      });
    }

    // Draggable Hook, Captions & CTA Guides
    const wireVerticalGuide = (el, key, fallbackY) => {
      if (!el) return;
      el.addEventListener("mousedown", (e) => {
        if (state.editor.drawMode || e.target.closest("button") || e.target.tagName === "INPUT") return;
        e.stopPropagation();
        const rect = canvas.getBoundingClientRect();
        const startY = e.clientY;
        const origTop = state.editor[key] !== null && state.editor[key] !== undefined ? state.editor[key] : fallbackY;
        const onMove = (ev) => {
          const dyPct = ((ev.clientY - startY) / rect.height) * 100;
          const next = Math.max(4, Math.min(88, Math.round((origTop + dyPct) * 10) / 10));
          state.editor[key] = next;
          el.style.top = `${next}%`;
        };
        const onUp = () => {
          window.removeEventListener("mousemove", onMove);
          window.removeEventListener("mouseup", onUp);
        };
        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
      });
    };
    wireVerticalGuide($("edHookGuide"), "hookY", 13);
    wireVerticalGuide($("edCaptionsGuide"), "captionsY", 72);
    wireVerticalGuide($("edCtaGuide"), "ctaY", 83);

    $("edHookGuide")?.addEventListener("dblclick", (e) => {
      e.stopPropagation();
      startInlineEdit($("edHookGuideText"), $("edHookTitle")?.value || "", (val) => {
        if ($("edHookTitle")) $("edHookTitle").value = val.trim();
      });
    });
    $("edCtaGuide")?.addEventListener("dblclick", (e) => {
      e.stopPropagation();
      startInlineEdit($("edCtaGuideText"), $("edCtaText")?.value || "", (val) => {
        if ($("edCtaText")) $("edCtaText").value = val.trim();
      });
    });

    canvas.querySelectorAll(".ov-box").forEach((box) => {
      box.addEventListener("dblclick", (e) => {
        e.stopPropagation();
        const ov = state.editor.overlays.find((o) => o.id === box.dataset.ovId);
        if (!ov || ov.mode !== "replace") return;
        startInlineEdit(box, ov.text || "", (val) => {
          ov.text = val;
          if ($("edOvText")) $("edOvText").value = val;
        });
      });
    });

    canvas.querySelectorAll(".ov-box").forEach((box) => {
      box.addEventListener("mousedown", (e) => {
        if (state.editor.drawMode) return;
        e.stopPropagation();
        const id = box.dataset.ovId;
        state.editor.selectedId = id;
        renderEditorOverlays();
        renderOverlayInspector();

        const ov = getSelectedOverlay();
        if (!ov) return;
        const rect = canvas.getBoundingClientRect();
        const isResize = e.target.classList.contains("ov-resize-handle");
        const startX = e.clientX;
        const startY = e.clientY;
        const orig = { x: ov.x, y: ov.y, w: ov.w, h: ov.h };

        const onMove = (ev) => {
          const dxPct = ((ev.clientX - startX) / rect.width) * 100;
          const dyPct = ((ev.clientY - startY) / rect.height) * 100;
          if (isResize) {
            ov.w = Math.max(8, Math.min(100 - orig.x, Math.round((orig.w + dxPct) * 10) / 10));
            ov.h = Math.max(5, Math.min(100 - orig.y, Math.round((orig.h + dyPct) * 10) / 10));
          } else {
            ov.x = Math.max(0, Math.min(100 - orig.w, Math.round((orig.x + dxPct) * 10) / 10));
            ov.y = Math.max(0, Math.min(100 - orig.h, Math.round((orig.y + dyPct) * 10) / 10));
          }
          const liveBox = canvas.querySelector(`.ov-box[data-ov-id="${id}"]`);
          if (liveBox) {
            liveBox.style.left = `${ov.x}%`;
            liveBox.style.top = `${ov.y}%`;
            liveBox.style.width = `${ov.w}%`;
            liveBox.style.height = `${ov.h}%`;
          }
        };
        const onUp = () => {
          window.removeEventListener("mousemove", onMove);
          window.removeEventListener("mouseup", onUp);
        };
        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
      });
    });
  }
}

function renderOverlayInspector() {
  const box = $("edOverlayInspector");
  const ov = getSelectedOverlay();
  if (!box) return;
  if (!ov) {
    box.style.display = "none";
    return;
  }
  box.style.display = "block";
  $("edOvMode").value = ov.mode || "replace";
  $("edOvCardStyle").value = ov.cardStyle || "solid_dark";
  $("edOvText").value = ov.text || "";
  if ($("edOvFontFamily")) $("edOvFontFamily").value = ov.fontFamily || $("edArabicFont")?.value || "cairo";
  $("edOvFontSize").value = ov.fontSize || 46;
  $("edOvFontSizeVal").textContent = `${ov.fontSize || 46}px`;
  $("edOvTextColor").value = ov.textColor || "#FFFFFF";
  $("edOvTextColorHex").textContent = ov.textColor || "#FFFFFF";
  $("edOvStart").value = ov.start || 0;
  $("edOvEnd").value = ov.end || 0;

  const isReplace = ov.mode === "replace";
  $("edOvStyleGroup").style.display = isReplace ? "flex" : "none";
  $("edOvTextGroup").style.display = isReplace ? "flex" : "none";
  $("edOvFontRow").style.display = isReplace ? "grid" : "none";
  if ($("edOvColorRow")) $("edOvColorRow").style.display = isReplace ? "grid" : "flex";
}

function setupEditor() {
  // 3-Tab Editor Switching
  document.querySelectorAll("#editorControlTabs .ed-tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchEditorTab(btn.dataset.edTab));
  });

  // Preview Source Switcher (Raw vs Rendered Output)
  document.querySelectorAll("#edPreviewSrcBar .guide-pill").forEach((btn) => {
    btn.addEventListener("click", () => setEditorPreviewSource(btn.dataset.previewSrc));
  });

  // Clean Canvas Guide Toggles (show element on video screen ONLY when clicked)
  document.querySelectorAll("#edGuideToggleBar .guide-pill").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.dataset.guide;
      state.editor.visibleGuides = state.editor.visibleGuides || {};
      state.editor.visibleGuides[key] = !state.editor.visibleGuides[key];
      btn.classList.toggle("active", Boolean(state.editor.visibleGuides[key]));
      renderEditorOverlays();
    });
  });

  $("edArabicFont")?.addEventListener("change", () => renderEditorOverlays());

  $("btnEditorBack")?.addEventListener("click", () => {
    const vid = $("edVideoPlayer");
    if (vid) { vid.pause(); vid.src = ""; }
    switchView("projects");
    refreshProjects();
  });

  $("btnDrawOverlay")?.addEventListener("click", () => {
    state.editor.drawMode = !state.editor.drawMode;
    updateDrawModeBtn();
  });

  // Draw rectangle directly on video canvas
  const canvas = $("edOverlayCanvas");
  if (canvas) {
    canvas.addEventListener("mousedown", (e) => {
      if (!state.editor.drawMode) return;
      const rect = canvas.getBoundingClientRect();
      const startXPct = ((e.clientX - rect.left) / rect.width) * 100;
      const startYPct = ((e.clientY - rect.top) / rect.height) * 100;

      const ghost = document.createElement("div");
      ghost.className = "ov-box mode-replace selected";
      ghost.style.left = `${startXPct}%`;
      ghost.style.top = `${startYPct}%`;
      ghost.style.width = "0%";
      ghost.style.height = "0%";
      canvas.appendChild(ghost);

      const onMove = (ev) => {
        const curXPct = Math.max(0, Math.min(100, ((ev.clientX - rect.left) / rect.width) * 100));
        const curYPct = Math.max(0, Math.min(100, ((ev.clientY - rect.top) / rect.height) * 100));
        const x = Math.min(startXPct, curXPct);
        const y = Math.min(startYPct, curYPct);
        const w = Math.abs(curXPct - startXPct);
        const h = Math.abs(curYPct - startYPct);
        ghost.style.left = `${x}%`;
        ghost.style.top = `${y}%`;
        ghost.style.width = `${w}%`;
        ghost.style.height = `${h}%`;
      };

      const onUp = (ev) => {
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
        ghost.remove();
        const curXPct = Math.max(0, Math.min(100, ((ev.clientX - rect.left) / rect.width) * 100));
        const curYPct = Math.max(0, Math.min(100, ((ev.clientY - rect.top) / rect.height) * 100));
        const x = Math.round(Math.min(startXPct, curXPct) * 10) / 10;
        const y = Math.round(Math.min(startYPct, curYPct) * 10) / 10;
        const w = Math.max(12, Math.round(Math.abs(curXPct - startXPct) * 10) / 10);
        const h = Math.max(6, Math.round(Math.abs(curYPct - startYPct) * 10) / 10);
        addOverlayPreset({ x, y, w, h, mode: "replace", text: "النص الجديد" });
      };

      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    });
  }

  $("btnQuickBottomText")?.addEventListener("click", () => {
    addOverlayPreset({ mode: "replace", x: 6, y: 74, w: 88, h: 13, text: "النص الجديد هنا", cardStyle: "solid_dark", textColor: "#FFFFFF" });
  });
  $("btnQuickTopText")?.addEventListener("click", () => {
    addOverlayPreset({ mode: "replace", x: 6, y: 12, w: 88, h: 11, text: "العنوان البديل", cardStyle: "solid_dark", textColor: "#FFD60A" });
  });
  $("btnQuickDelogo")?.addEventListener("click", () => {
    addOverlayPreset({ mode: "delogo", x: 68, y: 8, w: 24, h: 8, text: "" });
  });

  // Upload Image / Video Overlay (PiP)
  const uploadOverlayMedia = async (file, mediaMode) => {
    const proj = state.editor.project;
    if (!file || !proj) return;
    showToast(`⏳ جاري رفع ${mediaMode === "image" ? "الصورة" : "الفيديو"}...`);
    try {
      const res = await api(`/api/projects/${encodeURIComponent(proj.id)}/upload/broll`, {
        method: "POST",
        headers: { "x-filename": encodeURIComponent(file.name) },
        body: file,
      });
      addOverlayPreset({
        mode: mediaMode,
        mediaFile: res.name,
        mediaUrl: res.url,
        x: 16,
        y: 26,
        w: 68,
        h: 34,
        text: "",
      });
      showToast(`✅ تمت إضافة ${mediaMode === "image" ? "الصورة" : "الفيديو"} — اسحبها وحجمها كما تريد!`);
    } catch (err) {
      showToast("❌ فشل الرفع: " + err.message);
    }
  };
  $("btnQuickAddImage")?.addEventListener("click", () => $("edMediaImageInput")?.click());
  $("btnQuickAddVideo")?.addEventListener("click", () => $("edMediaVideoInput")?.click());
  $("btnScreenDraw")?.addEventListener("click", () => {
    state.editor.drawMode = !state.editor.drawMode;
    updateDrawModeBtn();
  });
  $("btnScreenImage")?.addEventListener("click", () => $("edMediaImageInput")?.click());
  $("btnScreenVideo")?.addEventListener("click", () => $("edMediaVideoInput")?.click());
  $("edMediaImageInput")?.addEventListener("change", (e) => {
    const f = e.target.files?.[0];
    if (f) uploadOverlayMedia(f, "image");
    e.target.value = "";
  });
  $("edMediaVideoInput")?.addEventListener("change", (e) => {
    const f = e.target.files?.[0];
    if (f) uploadOverlayMedia(f, "video");
    e.target.value = "";
  });

  // Live sync title/hook/CTA & reset positions
  $("edHookTitle")?.addEventListener("input", () => renderEditorOverlays());
  $("edCtaText")?.addEventListener("input", () => renderEditorOverlays());
  $("edShowHookCard")?.addEventListener("change", () => renderEditorOverlays());
  $("edSalawatOutro")?.addEventListener("change", () => renderEditorOverlays());
  $("btnResetPositions")?.addEventListener("click", () => {
    state.editor.hookY = null;
    state.editor.captionsY = null;
    state.editor.ctaY = null;
    state.editor.watermarkX = null;
    state.editor.watermarkY = null;
    state.editor.showWatermark = true;
    renderEditorOverlays();
    showToast("↺ تم إعادة ضبط أماكن كل العناصر");
  });

  // Inspector bindings
  $("edOvMode")?.addEventListener("change", (e) => {
    const ov = getSelectedOverlay();
    if (!ov) return;
    ov.mode = e.target.value;
    renderEditorOverlays();
    renderOverlayInspector();
  });
  $("edOvCardStyle")?.addEventListener("change", (e) => {
    const ov = getSelectedOverlay();
    if (!ov) return;
    ov.cardStyle = e.target.value;
    renderEditorOverlays();
  });
  $("edOvText")?.addEventListener("input", (e) => {
    const ov = getSelectedOverlay();
    if (!ov) return;
    ov.text = e.target.value;
    renderEditorOverlays();
  });
  $("edOvFontFamily")?.addEventListener("change", (e) => {
    const ov = getSelectedOverlay();
    if (!ov) return;
    ov.fontFamily = e.target.value;
    renderEditorOverlays();
  });
  $("edOvFontSize")?.addEventListener("input", (e) => {
    const ov = getSelectedOverlay();
    if (!ov) return;
    ov.fontSize = Number(e.target.value);
    $("edOvFontSizeVal").textContent = `${ov.fontSize}px`;
    renderEditorOverlays();
  });
  $("edOvTextColor")?.addEventListener("input", (e) => {
    const ov = getSelectedOverlay();
    if (!ov) return;
    ov.textColor = e.target.value;
    $("edOvTextColorHex").textContent = ov.textColor;
    renderEditorOverlays();
  });
  $("edOvStart")?.addEventListener("input", (e) => {
    const ov = getSelectedOverlay();
    if (ov) ov.start = Math.max(0, Number(e.target.value) || 0);
  });
  $("edOvEnd")?.addEventListener("input", (e) => {
    const ov = getSelectedOverlay();
    if (ov) ov.end = Math.max(0, Number(e.target.value) || 0);
  });
  $("btnEdGrabStart")?.addEventListener("click", () => {
    const ov = getSelectedOverlay();
    const vid = $("edVideoPlayer");
    if (ov && vid) {
      ov.start = Math.round((vid.currentTime || 0) * 10) / 10;
      $("edOvStart").value = ov.start;
    }
  });
  $("btnEdGrabEnd")?.addEventListener("click", () => {
    const ov = getSelectedOverlay();
    const vid = $("edVideoPlayer");
    if (ov && vid) {
      ov.end = Math.round((vid.currentTime || 0) * 10) / 10;
      $("edOvEnd").value = ov.end;
    }
  });
  $("btnEdDeleteOv")?.addEventListener("click", () => {
    if (!state.editor.selectedId) return;
    state.editor.overlays = state.editor.overlays.filter((o) => o.id !== state.editor.selectedId);
    state.editor.selectedId = state.editor.overlays[0]?.id || null;
    renderEditorOverlays();
    renderOverlayInspector();
  });

  $("btnEditorSaveOnly")?.addEventListener("click", () => saveEditorSettings(false));
  $("btnEditorRerender")?.addEventListener("click", () => saveEditorSettings(true));
  $("btnEditorDelete")?.addEventListener("click", () => {
    const p = state.editor.project;
    if (p) deleteProject(p.id, encodeURIComponent(p.settings?.title || p.id));
  });

  // Live Crop, Zoom & Trim bindings
  ["edFitMode", "edCropZoom", "edCropPanX", "edCropPanY", "edCropTop", "edCropBottom", "edCropLeft", "edCropRight"].forEach((id) => {
    $(id)?.addEventListener("input", updateEditorCropPreview);
    $(id)?.addEventListener("change", updateEditorCropPreview);
  });
  ["edTrimStart", "edTrimEnd"].forEach((id) => {
    $(id)?.addEventListener("input", renderEditorTimeline);
    $(id)?.addEventListener("change", renderEditorTimeline);
  });
  $("btnEdResetCrop")?.addEventListener("click", () => {
    if ($("edFitMode")) $("edFitMode").value = "cover";
    if ($("edCropZoom")) $("edCropZoom").value = 1;
    if ($("edCropPanX")) $("edCropPanX").value = 0;
    if ($("edCropPanY")) $("edCropPanY").value = 0;
    if ($("edCropTop")) $("edCropTop").value = 0;
    if ($("edCropBottom")) $("edCropBottom").value = 0;
    if ($("edCropLeft")) $("edCropLeft").value = 0;
    if ($("edCropRight")) $("edCropRight").value = 0;
    if ($("edTrimStart")) $("edTrimStart").value = 0;
    if ($("edTrimEnd")) $("edTrimEnd").value = 0;
    state.editor.cutSegments = [];
    renderEditorCutSegments();
    updateEditorCropPreview();
    renderEditorTimeline();
    showToast("↺ تم إعادة ضبط القصّ والزوم والمدة");
  });

  // Draggable 4-Edge Crop Box handles directly on video screen
  document.querySelectorAll(".crop-handle[data-crop-edge]").forEach((handle) => {
    handle.addEventListener("mousedown", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const edge = handle.dataset.cropEdge;
      const box = getRenderedVideoBox();
      const frameRect = $("edPhoneFrame")?.getBoundingClientRect();
      if (!frameRect || box.w <= 10 || box.h <= 10) return;

      const onMove = (ev) => {
        const relX = ev.clientX - frameRect.left;
        const relY = ev.clientY - frameRect.top;
        if (edge === "top") {
          const pct = Math.max(0, Math.min(45, Math.round(((relY - box.y) / box.h) * 100)));
          if ($("edCropTop")) $("edCropTop").value = pct;
        } else if (edge === "bottom") {
          const pct = Math.max(0, Math.min(45, Math.round(((box.y + box.h - relY) / box.h) * 100)));
          if ($("edCropBottom")) $("edCropBottom").value = pct;
        } else if (edge === "left") {
          const pct = Math.max(0, Math.min(45, Math.round(((relX - box.x) / box.w) * 100)));
          if ($("edCropLeft")) $("edCropLeft").value = pct;
        } else if (edge === "right") {
          const pct = Math.max(0, Math.min(45, Math.round(((box.x + box.w - relX) / box.w) * 100)));
          if ($("edCropRight")) $("edCropRight").value = pct;
        }
        updateEditorCropPreview();
      };
      const onUp = () => {
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    });
  });

  // Apply Real FFmpeg Crop Preview -> cropped parts vanish & remaining video fills 9:16 cleanly!
  $("btnApplyCropPreview")?.addEventListener("click", async () => {
    const proj = state.editor.project;
    if (!proj) return;
    const btn = $("btnApplyCropPreview");
    btn.disabled = true;
    btn.textContent = "⏳ جاري قصّ المعاينة...";
    try {
      const res = await api(`/api/projects/${encodeURIComponent(proj.id)}/crop-preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fitMode: $("edFitMode")?.value || "cover",
          cropZoom: Number($("edCropZoom")?.value || 1),
          cropPanX: Number($("edCropPanX")?.value || 0),
          cropPanY: Number($("edCropPanY")?.value || 0),
          cropTop: Number($("edCropTop")?.value || 0),
          cropBottom: Number($("edCropBottom")?.value || 0),
          cropLeft: Number($("edCropLeft")?.value || 0),
          cropRight: Number($("edCropRight")?.value || 0),
        }),
      });
      state.editor.cropPreviewUrl = res.previewUrl;
      switchEditorTab("text");
      setEditorPreviewSource("cropped");
      showToast("✅ تم قصّ الفيديو! الآن وازن النصوص واللوجو على المقاس الجديد بدقة 100%");
    } catch (err) {
      showToast("❌ " + err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "✅ تطبيق القصّ على المعاينة";
    }
  });

  // CapCut-style Visual Timeline Bar
  setupEditorTimeline();
  $("btnEdGrabTrimStart")?.addEventListener("click", () => {
    const vid = $("edVideoPlayer");
    if (vid && $("edTrimStart")) $("edTrimStart").value = Math.round((vid.currentTime || 0) * 10) / 10;
  });
  $("btnEdGrabTrimEnd")?.addEventListener("click", () => {
    const vid = $("edVideoPlayer");
    if (vid && $("edTrimEnd")) $("edTrimEnd").value = Math.round((vid.currentTime || 0) * 10) / 10;
  });

  // Cut Middle Segments
  $("btnEdGrabCutStart")?.addEventListener("click", () => {
    const vid = $("edVideoPlayer");
    if (vid && $("edCutSegStart")) $("edCutSegStart").value = Math.round((vid.currentTime || 0) * 10) / 10;
  });
  $("btnEdGrabCutEnd")?.addEventListener("click", () => {
    const vid = $("edVideoPlayer");
    if (vid && $("edCutSegEnd")) $("edCutSegEnd").value = Math.round((vid.currentTime || 0) * 10) / 10;
  });
  $("btnEdAddCutSeg")?.addEventListener("click", () => {
    const s = Math.max(0, Number($("edCutSegStart")?.value || 0));
    const e = Math.max(0, Number($("edCutSegEnd")?.value || 0));
    if (e <= s + 0.15) {
      showToast("⚠️ يجب أن يكون وقت النهاية أكبر من وقت البداية");
      return;
    }
    state.editor.cutSegments = state.editor.cutSegments || [];
    state.editor.cutSegments.push({ start: s, end: e });
    if ($("edCutSegStart")) $("edCutSegStart").value = "";
    if ($("edCutSegEnd")) $("edCutSegEnd").value = "";
    renderEditorCutSegments();
    showToast(`✂️ سيتم حذف الجزء من ${s}s إلى ${e}s أثناء الرندر`);
  });

  // Audio source tabs (original / custom / tts)
  document.querySelectorAll("#edAudioSourceTabs .audio-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      state.editor.audioSource = tab.dataset.source;
      syncAudioSourceTabs();
    });
  });

  // Upload custom voiceover
  $("btnEdPickVoice")?.addEventListener("click", () => $("edVoiceFileInput")?.click());
  $("edVoiceFileInput")?.addEventListener("change", async () => {
    const f = $("edVoiceFileInput").files?.[0];
    const proj = state.editor.project;
    if (!f || !proj) return;
    $("edVoiceFileStatus").textContent = "⏳ جاري الرفع...";
    try {
      const res = await api(`/api/projects/${encodeURIComponent(proj.id)}/upload/voice`, {
        method: "POST",
        headers: { "x-filename": encodeURIComponent(f.name) },
        body: f,
      });
      state.editor.customVoiceName = f.name;
      $("edVoiceFileStatus").textContent = `✅ ${f.name} (${formatBytes(res.size)})`;
      const prev = $("edCustomVoicePreview");
      if (prev && res.voiceUrl) {
        prev.src = `${res.voiceUrl}?t=${Date.now()}`;
        prev.style.display = "block";
      }
      showToast("✅ تم رفع الصوت بنجاح!");
    } catch (err) {
      $("edVoiceFileStatus").textContent = "❌ فشل الرفع";
      showToast("❌ " + err.message);
    }
  });

  // Generate AI Arabic TTS with pronunciation normalization
  $("btnEdGenerateTts")?.addEventListener("click", async () => {
    const proj = state.editor.project;
    const text = $("edTtsText")?.value.trim();
    if (!proj) return;
    if (!text) {
      showToast("⚠️ اكتب النص العربي أولاً");
      return;
    }
    const btn = $("btnEdGenerateTts");
    btn.disabled = true;
    btn.textContent = "⏳ جاري التوليد ومعالجة النطق...";
    try {
      const res = await api(`/api/projects/${encodeURIComponent(proj.id)}/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          voice: $("edTtsVoice")?.value || "salma",
          rate: $("edTtsRate")?.value || "+0%",
          voicePreset: $("edVoicePreset")?.value || "studio",
          updateCaptions: $("edTtsUpdateCaptions")?.checked !== false,
        }),
      });
      const prev = $("edTtsPreview");
      if (prev && res.voiceUrl) {
        prev.src = res.voiceUrl;
        prev.style.display = "block";
        prev.play().catch(() => {});
      }
      showToast("✅ تم توليد الصوت ومعالجة النطق!");
    } catch (err) {
      showToast("❌ " + err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "🎙️ توليد ومعالجة النطق الآن";
    }
  });

  // Timed SFX
  $("btnEdGrabSfxTime")?.addEventListener("click", () => {
    const vid = $("edVideoPlayer");
    if (vid) $("edSfxTime").value = Math.round((vid.currentTime || 0) * 10) / 10;
  });
  $("btnEdAddSfx")?.addEventListener("click", () => {
    const file = $("edSfxFile")?.value || "whoosh.wav";
    const time = Math.max(0, Number($("edSfxTime")?.value) || 0);
    state.editor.customSfx = state.editor.customSfx || [];
    state.editor.customSfx.push({ file, time, volume_db: -10 });
    renderEditorSfx();
  });
}

function syncAudioSourceTabs() {
  const src = state.editor.audioSource || "original";
  document.querySelectorAll("#edAudioSourceTabs .audio-tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.source === src);
  });
  if ($("edAudioCustomPanel")) $("edAudioCustomPanel").style.display = src === "custom" ? "block" : "none";
  if ($("edAudioTtsPanel")) $("edAudioTtsPanel").style.display = src === "tts" ? "block" : "none";
}

function renderEditorSfx() {
  const list = $("edSfxList");
  if (!list) return;
  const items = state.editor.customSfx || [];
  if (!items.length) {
    list.innerHTML = `<span class="ed-hint" style="margin:0;">لا توجد مؤثرات صوتية مخصصة بعد.</span>`;
    return;
  }
  list.innerHTML = items.map((s, idx) => `
    <span class="ov-chip" style="display:inline-flex; align-items:center; gap:6px;">
      🔊 ${s.file.replace(".wav", "")} @ ${s.time}s
      <button type="button" data-del-sfx="${idx}" style="background:none;border:none;color:var(--red);cursor:pointer;font-weight:900;">✕</button>
    </span>
  `).join("");
  list.querySelectorAll("[data-del-sfx]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = Number(btn.dataset.delSfx);
      state.editor.customSfx.splice(idx, 1);
      renderEditorSfx();
    });
  });
}

function renderEditorCutSegments() {
  const list = $("edCutSegList");
  if (!list) return;
  const segs = state.editor.cutSegments || [];
  if (!segs.length) {
    list.innerHTML = `<span class="ed-hint" style="margin:0;">لا توجد أجزاء محذوفة من المنتصف.</span>`;
    return;
  }
  list.innerHTML = segs.map((seg, idx) => `
    <span class="ov-chip" style="display:inline-flex; align-items:center; gap:6px;">
      ✂️ حذف ${seg.start}s → ${seg.end}s
      <button type="button" data-del-cut="${idx}" style="background:none;border:none;color:var(--red);cursor:pointer;font-weight:900;">✕</button>
    </span>
  `).join("");
  list.querySelectorAll("[data-del-cut]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.editor.cutSegments.splice(Number(btn.dataset.delCut), 1);
      renderEditorCutSegments();
    });
  });
}

function fmtSec(sec) {
  const s = Math.max(0, Number(sec) || 0);
  const m = Math.floor(s / 60);
  const rem = (s % 60).toFixed(1).padStart(4, "0");
  return `${String(m).padStart(2, "0")}:${rem}`;
}

function getRenderedVideoBox() {
  const frame = $("edPhoneFrame");
  const vid = $("edVideoPlayer");
  if (!frame) return { x: 0, y: 0, w: 330, h: 586, fw: 330, fh: 586 };
  const fw = frame.clientWidth || 330;
  const fh = frame.clientHeight || 586;
  const vw = vid?.videoWidth || 9;
  const vh = vid?.videoHeight || 16;
  const frameRatio = fw / fh;
  const vidRatio = vw / vh;
  let w = fw, h = fh, x = 0, y = 0;
  if (vidRatio > frameRatio) {
    w = fw;
    h = fw / vidRatio;
    y = (fh - h) / 2;
  } else {
    h = fh;
    w = fh * vidRatio;
    x = (fw - w) / 2;
  }
  return { x, y, w, h, fw, fh };
}

function setupEditorTimeline() {
  const bar = $("edTimelineBar");
  const vid = $("edVideoPlayer");

  $("btnTlCutMode")?.addEventListener("click", () => {
    state.editor.tlCutMode = !state.editor.tlCutMode;
    $("btnTlCutMode")?.classList.toggle("active", state.editor.tlCutMode);
    bar?.classList.toggle("cut-mode", state.editor.tlCutMode);
    if (state.editor.tlCutMode) {
      showToast("✂️ اسحب بالماوس على الشريط الزمني لتحديد الجزء المراد حذفه");
    }
  });

  $("btnTlSetStart")?.addEventListener("click", () => {
    if (!vid) return;
    if ($("edTrimStart")) $("edTrimStart").value = Math.round((vid.currentTime || 0) * 10) / 10;
    renderEditorTimeline();
    showToast(`✂️ بداية الفيديو: ${fmtSec(vid.currentTime)}`);
  });

  $("btnTlSetEnd")?.addEventListener("click", () => {
    if (!vid) return;
    if ($("edTrimEnd")) $("edTrimEnd").value = Math.round((vid.currentTime || 0) * 10) / 10;
    renderEditorTimeline();
    showToast(`✂️ نهاية الفيديو: ${fmtSec(vid.currentTime)}`);
  });

  if (vid) {
    vid.addEventListener("timeupdate", () => {
      const dur = vid.duration || 0;
      const t = vid.currentTime || 0;
      if ($("edTlTimeText")) $("edTlTimeText").textContent = `${fmtSec(t)} / ${fmtSec(dur)}`;
      if ($("edTlPlayhead") && dur > 0) {
        $("edTlPlayhead").style.left = `${Math.min(100, (t / dur) * 100)}%`;
      }
      // CapCut-style live preview: auto-skip over red deleted segments while playing raw video
      if (!vid.paused && state.editor.previewMode === "raw" && dur > 0) {
        const trimEnd = Number($("edTrimEnd")?.value || 0);
        if (trimEnd > 0.4 && t >= trimEnd) {
          vid.pause();
          return;
        }
        for (const seg of (state.editor.cutSegments || [])) {
          if (t >= seg.start && t < seg.end - 0.08) {
            vid.currentTime = Math.min(dur - 0.05, seg.end);
            break;
          }
        }
      }
    });
  }

  if (bar) {
    bar.addEventListener("mousedown", (e) => {
      if (e.target.classList.contains("tl-cut-seg")) return;
      const dur = vid?.duration || 0;
      if (dur <= 0) return;
      const rect = bar.getBoundingClientRect();
      const pctToSec = (clientX) => {
        const p = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
        return Math.round(p * dur * 10) / 10;
      };

      if (!state.editor.tlCutMode) {
        if (vid) vid.currentTime = pctToSec(e.clientX);
        return;
      }

      // Drag to select a red cut segment
      const startSec = pctToSec(e.clientX);
      const dragSel = $("edTlDragSel");
      const updateDrag = (curX) => {
        const curSec = pctToSec(curX);
        const s = Math.min(startSec, curSec);
        const en = Math.max(startSec, curSec);
        if (dragSel) {
          dragSel.style.display = "block";
          dragSel.style.left = `${(s / dur) * 100}%`;
          dragSel.style.width = `${((en - s) / dur) * 100}%`;
        }
      };
      updateDrag(e.clientX);

      const onMove = (ev) => updateDrag(ev.clientX);
      const onUp = (ev) => {
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
        if (dragSel) dragSel.style.display = "none";
        const endSec = pctToSec(ev.clientX);
        const s = Math.min(startSec, endSec);
        const en = Math.max(startSec, endSec);
        if (en > s + 0.2) {
          state.editor.cutSegments = state.editor.cutSegments || [];
          state.editor.cutSegments.push({ start: s, end: en });
          renderEditorCutSegments();
          renderEditorTimeline();
          showToast(`✂️ تم تحديد حذف الجزء ${fmtSec(s)} → ${fmtSec(en)}`);
        }
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    });
  }
}

function renderEditorTimeline() {
  const vid = $("edVideoPlayer");
  const dur = vid?.duration || 0;
  if ($("edTlTimeText")) $("edTlTimeText").textContent = `${fmtSec(vid?.currentTime || 0)} / ${fmtSec(dur)}`;
  if (dur <= 0) return;

  const ts = Math.max(0, Math.min(dur, Number($("edTrimStart")?.value || 0)));
  const rawTe = Number($("edTrimEnd")?.value || 0);
  const te = rawTe > ts + 0.2 ? Math.min(dur, rawTe) : dur;

  if ($("edTlTrimLeft")) $("edTlTrimLeft").style.width = `${(ts / dur) * 100}%`;
  if ($("edTlTrimRight")) $("edTlTrimRight").style.width = `${((dur - te) / dur) * 100}%`;

  const layer = $("edTlCutsLayer");
  if (layer) {
    layer.innerHTML = (state.editor.cutSegments || []).map((seg, idx) => {
      const leftPct = Math.max(0, Math.min(100, (seg.start / dur) * 100));
      const widthPct = Math.max(1, Math.min(100 - leftPct, ((seg.end - seg.start) / dur) * 100));
      return `<div class="tl-cut-seg" data-tl-cut-idx="${idx}" style="left:${leftPct}%; width:${widthPct}%;" title="جزء محذوف (${seg.start}s → ${seg.end}s) — اضغط لإلغاء الحذف"></div>`;
    }).join("");
    layer.querySelectorAll(".tl-cut-seg").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        state.editor.cutSegments.splice(Number(el.dataset.tlCutIdx), 1);
        renderEditorCutSegments();
        renderEditorTimeline();
        showToast("↩️ تم إلغاء حذف هذا الجزء");
      });
    });
  }
}

function updateEditorCropPreview() {
  const fit = $("edFitMode")?.value || "cover";
  const zoom = Number($("edCropZoom")?.value || 1);
  const panX = Number($("edCropPanX")?.value || 0);
  const panY = Number($("edCropPanY")?.value || 0);
  const top = Number($("edCropTop")?.value || 0);
  const bottom = Number($("edCropBottom")?.value || 0);
  const left = Number($("edCropLeft")?.value || 0);
  const right = Number($("edCropRight")?.value || 0);

  if ($("edCropZoomVal")) $("edCropZoomVal").textContent = `${zoom.toFixed(2)}×`;
  if ($("edCropPanXVal")) $("edCropPanXVal").textContent = `${panX}%`;
  if ($("edCropPanYVal")) $("edCropPanYVal").textContent = `${panY}%`;
  if ($("edCropTopVal")) $("edCropTopVal").textContent = `${top}%`;
  if ($("edCropBottomVal")) $("edCropBottomVal").textContent = `${bottom}%`;
  if ($("edCropLeftVal")) $("edCropLeftVal").textContent = `${left}%`;
  if ($("edCropRightVal")) $("edCropRightVal").textContent = `${right}%`;

  const vid = $("edVideoPlayer");
  const maskLayer = $("edCropMaskLayer");
  const showCropBox = state.editor.activeTab === "crop" && state.editor.previewMode === "raw";

  if (maskLayer) maskLayer.style.display = showCropBox ? "block" : "none";

  if (vid) {
    if (showCropBox) {
      // Show 100% of raw video un-distorted so the 4-edge Crop Box matches FFmpeg pixel-for-pixel!
      vid.style.objectFit = "contain";
      vid.style.transform = "none";
      vid.style.clipPath = "none";

      const box = getRenderedVideoBox();
      const cx = box.x + (box.w * left) / 100;
      const cy = box.y + (box.h * top) / 100;
      const cw = Math.max(20, box.w * (1 - (left + right) / 100));
      const ch = Math.max(20, box.h * (1 - (top + bottom) / 100));

      const rectEl = $("edCropRect");
      if (rectEl) {
        rectEl.style.left = `${cx}px`;
        rectEl.style.top = `${cy}px`;
        rectEl.style.width = `${cw}px`;
        rectEl.style.height = `${ch}px`;
      }
      if ($("cropShadeTop")) {
        Object.assign($("cropShadeTop").style, { left: "0px", top: "0px", width: `${box.fw}px`, height: `${Math.max(0, cy)}px` });
      }
      if ($("cropShadeBottom")) {
        Object.assign($("cropShadeBottom").style, { left: "0px", top: `${cy + ch}px`, width: `${box.fw}px`, height: `${Math.max(0, box.fh - (cy + ch))}px` });
      }
      if ($("cropShadeLeft")) {
        Object.assign($("cropShadeLeft").style, { left: "0px", top: `${cy}px`, width: `${Math.max(0, cx)}px`, height: `${ch}px` });
      }
      if ($("cropShadeRight")) {
        Object.assign($("cropShadeRight").style, { left: `${cx + cw}px`, top: `${cy}px`, width: `${Math.max(0, box.fw - (cx + cw))}px`, height: `${ch}px` });
      }
    } else {
      vid.style.objectFit = "cover";
      vid.style.transform = "none";
      vid.style.clipPath = "none";
    }
  }
}

async function saveEditorSettings(rerenderAfter) {
  const proj = state.editor.project;
  if (!proj) return;
  const prev = proj.settings || {};
  const fitMode = $("edFitMode")?.value || "cover";
  const cropZoom = Number($("edCropZoom")?.value || 1);
  const cropPanX = Number($("edCropPanX")?.value || 0);
  const cropPanY = Number($("edCropPanY")?.value || 0);
  const cropTop = Number($("edCropTop")?.value || 0);
  const cropBottom = Number($("edCropBottom")?.value || 0);
  const cropLeft = Number($("edCropLeft")?.value || 0);
  const cropRight = Number($("edCropRight")?.value || 0);
  const trimStart = Math.max(0, Number($("edTrimStart")?.value || 0));
  const trimEnd = Math.max(0, Number($("edTrimEnd")?.value || 0));

  const cutSegments = state.editor.cutSegments || [];
  const trimChanged =
    trimStart !== Number(prev.trimStart || 0) ||
    trimEnd !== Number(prev.trimEnd || 0) ||
    JSON.stringify(cutSegments) !== JSON.stringify(prev.cutSegments || []);
  const cropChanged =
    fitMode !== (prev.fitMode || "cover") ||
    cropZoom !== Number(prev.cropZoom || 1) ||
    cropPanX !== Number(prev.cropPanX || 0) ||
    cropPanY !== Number(prev.cropPanY || 0) ||
    cropTop !== Number(prev.cropTop || 0) ||
    cropBottom !== Number(prev.cropBottom || 0) ||
    cropLeft !== Number(prev.cropLeft || 0) ||
    cropRight !== Number(prev.cropRight || 0);
  if (trimChanged) state.editor.trimDirty = true;
  if (cropChanged) state.editor.cropDirty = true;

  const updated = {
    ...prev,
    fitMode,
    cropZoom,
    cropPanX,
    cropPanY,
    cropTop,
    cropBottom,
    cropLeft,
    cropRight,
    trimStart,
    trimEnd,
    cutSegments,
    showCaptions: $("edShowCaptions")?.checked !== false,
    hookTitle: $("edHookTitle")?.value.trim() || "",
    arabicFont: $("edArabicFont")?.value || "cairo",
    hookY: state.editor.hookY,
    captionsY: state.editor.captionsY,
    ctaY: state.editor.ctaY,
    watermarkX: state.editor.watermarkX,
    watermarkY: state.editor.watermarkY,
    showWatermark: state.editor.showWatermark !== false,
    ctaText: $("edCtaText")?.value.trim() || "",
    showHookCard: $("edShowHookCard")?.checked !== false,
    salawatOutro: Boolean($("edSalawatOutro")?.checked),
    overlays: state.editor.overlays,
    audioSource: state.editor.audioSource || "original",
    muteOriginal: Boolean($("edMuteOriginal")?.checked),
    voicePreset: $("edVoicePreset")?.value || "studio",
    denoise: $("edDenoise")?.value || "light",
    ttsText: $("edTtsText")?.value.trim() || "",
    ttsVoice: $("edTtsVoice")?.value || "salma",
    ttsRate: $("edTtsRate")?.value || "+0%",
    customVoiceName: state.editor.customVoiceName || prev.customVoiceName || "",
    customSfx: state.editor.customSfx || [],
  };
  try {
    const res = await api(`/api/projects/${encodeURIComponent(proj.id)}/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updated),
    });
    state.editor.project = res.project;
    if (!rerenderAfter) {
      showToast("✅ تم حفظ التعديلات!");
      return;
    }
    const vid = $("edVideoPlayer");
    if (vid) vid.pause();
    const isRaw = !res.project.files?.hasOutput && !res.project.files?.hasCut;
    const task = (isRaw || state.editor.trimDirty) ? "auto_full" : "rerender";
    state.editor.trimDirty = false;
    state.editor.cropDirty = false;
    showToast(task === "auto_full" ? "🚀 جاري بدء المونتاج والرندر النهائي..." : "⚡ جاري تطبيق التعديلات والقصّ (رندر سريع)...");
    const { jobId } = await api(`/api/projects/${encodeURIComponent(proj.id)}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task }),
    });
    state.currentJob = { jobId, projectId: proj.id };
    showProgressModal(proj.id);
    startPolling(jobId);
  } catch (err) {
    showToast("❌ " + err.message);
  }
}

// ── Boot ───────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", init);
