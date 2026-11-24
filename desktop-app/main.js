// main.js — نقطة دخول Electron لاستوديو Avesta
const { app, BrowserWindow, shell, ipcMain, dialog, session } = require('electron');
const path   = require('path');
const { spawn, execFileSync } = require('child_process');
const http   = require('http');
const fs     = require('fs');

// ──────────────────────────────────────────────
// إعدادات
// ──────────────────────────────────────────────
const ROOT       = path.resolve(__dirname, '..');
const SERVER_MJS = path.join(ROOT, 'studio', 'server.mjs');
const PORT       = Number(process.env.STUDIO_PORT || 3456);
const STUDIO_URL = `http://localhost:${PORT}`;

let mainWindow = null;
let serverProc = null;

// ──────────────────────────────────────────────
// تشغيل خادم Node (server.mjs)
// ──────────────────────────────────────────────
function startServer() {
  if (!fs.existsSync(SERVER_MJS)) {
    dialog.showErrorBox('خطأ', `ملف الخادم غير موجود:\n${SERVER_MJS}`);
    app.quit();
    return;
  }

  // If server is already running on PORT, reuse it instead of spawning a duplicate
  http.get(STUDIO_URL, () => {
    console.log('[server] Already running on', STUDIO_URL);
  }).on('error', () => {
    serverProc = spawn('node', [SERVER_MJS], {
      cwd:   ROOT,
      stdio: 'pipe',
      windowsHide: true,
      env:   { ...process.env, STUDIO_PORT: String(PORT) },
    });

    serverProc.stdout.on('data', (d) => console.log('[server]', d.toString().trim()));
    serverProc.stderr.on('data', (d) => console.error('[server]', d.toString().trim()));
    serverProc.on('close', (code) => {
      console.log('[server] Exit code:', code);
    });
  });
}

// ──────────────────────────────────────────────
// انتظر حتى يستجيب الخادم ثم افتح النافذة
// ──────────────────────────────────────────────
function waitForServer(tries = 0) {
  http.get(STUDIO_URL, (res) => {
    // الخادم جاهز
    if (mainWindow) {
      mainWindow.loadURL(STUDIO_URL);
    }
  }).on('error', () => {
    if (tries < 60) {
      setTimeout(() => waitForServer(tries + 1), 500);
    } else {
      dialog.showErrorBox('تعذّر الاتصال', `لم يستجب الخادم على ${STUDIO_URL}\nتأكد أن المنفذ ${PORT} غير مستخدم.`);
      app.quit();
    }
  });
}

// ──────────────────────────────────────────────
// إنشاء النافذة الرئيسية
// ──────────────────────────────────────────────
function createWindow() {
  const icoPath = path.join(ROOT, 'assets', 'logo', 'app-icon.ico');
  const pngPath = path.join(ROOT, 'assets', 'logo', 'logo.png');
  const winIcon = fs.existsSync(icoPath) ? icoPath : (fs.existsSync(pngPath) ? pngPath : undefined);

  mainWindow = new BrowserWindow({
    width:           1400,
    height:          900,
    minWidth:        900,
    minHeight:       600,
    backgroundColor: '#080A0F',
    titleBarStyle:   'default',
    title:           'Avesta AI Video Studio',
    icon:            winIcon,
    webPreferences: {
      preload:          path.join(__dirname, 'preload.js'),
      nodeIntegration:  false,
      contextIsolation: true,
      webSecurity:      false,   // ضروري لتحميل ملفات الميديا المحلية
    },
  });

  // شاشة تحميل مؤقتة أثناء انتظار الخادم
  mainWindow.loadURL(`data:text/html;charset=utf-8,
    <html dir="rtl" style="margin:0;background:#080A0F;display:flex;align-items:center;justify-content:center;height:100vh;font-family:Cairo,Arial,sans-serif;color:#FFD60A">
      <div style="text-align:center">
        <div style="font-size:48px;margin-bottom:16px">🎬</div>
        <div style="font-size:24px;font-weight:700">Avesta AI Studio</div>
        <div style="font-size:14px;margin-top:12px;color:#888">جاري تشغيل الخادم...</div>
      </div>
    </html>
  `);

  // بدء انتظار الخادم بعد نصف ثانية
  setTimeout(() => waitForServer(), 500);

  // فتح روابط http خارجية في المتصفح الافتراضي
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http') && !url.startsWith(STUDIO_URL)) {
      shell.openExternal(url);
      return { action: 'deny' };
    }
    return { action: 'allow' };
  });

  mainWindow.on('closed', () => { mainWindow = null; });
}

function getExportFolder() {
  try {
    const cfgPath = path.join(ROOT, 'studio', 'brand-config.json');
    if (fs.existsSync(cfgPath)) {
      const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
      const custom = String(cfg?.defaults?.exportFolder || '').trim();
      if (custom) return custom;
    }
  } catch {}
  return 'D:\\غناوي هلنا';
}

// ──────────────────────────────────────────────
// IPC — أوامر من الواجهة
// ──────────────────────────────────────────────
ipcMain.on('close-app',    () => { if (mainWindow) mainWindow.close(); });
ipcMain.on('minimize-app', () => { if (mainWindow) mainWindow.minimize(); });
ipcMain.on('maximize-app', () => {
  if (!mainWindow) return;
  mainWindow.isMaximized() ? mainWindow.unmaximize() : mainWindow.maximize();
});
ipcMain.handle('pick-video-from-downloads', async () => {
  const downloadsDir = app.getPath('downloads');
  const res = await dialog.showOpenDialog(mainWindow, {
    title: 'اختر فيديو من التنزيلات (Downloads)',
    defaultPath: downloadsDir,
    properties: ['openFile'],
    filters: [
      { name: 'فيديوهات', extensions: ['mp4', 'mov', 'mkv', 'webm', 'avi', 'm4v'] },
      { name: 'كل الملفات', extensions: ['*'] },
    ],
  });
  if (res.canceled || !res.filePaths || !res.filePaths.length) return null;
  const filePath = res.filePaths[0];
  let size = 0;
  try { size = fs.statSync(filePath).size; } catch {}
  return { path: filePath, name: path.basename(filePath), size };
});

// ──────────────────────────────────────────────
// دورة حياة التطبيق
// ──────────────────────────────────────────────
app.whenReady().then(() => {
  // حفظ أي تحميل مباشر من داخل البرنامج تلقائياً في D:\غناوي هلنا
  session.defaultSession.on('will-download', (event, item) => {
    try {
      const exportDir = getExportFolder();
      fs.mkdirSync(exportDir, { recursive: true });
      const rawName = (item.getFilename() || 'video.mp4').replace(/[<>:"/\\|?*]+/g, ' ').trim();
      item.setSavePath(path.join(exportDir, rawName));
    } catch (e) {
      console.error('[download] savePath error:', e);
    }
  });

  startServer();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  // إيقاف خادم Node عند إغلاق التطبيق
  if (serverProc) {
    try { serverProc.kill(); } catch {}
  }
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  if (serverProc) {
    try { serverProc.kill(); } catch {}
  }
});

