// preload.js — واجهة آمنة بين Node.js و Renderer
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  closeApp:   () => ipcRenderer.send('close-app'),
  minimizeApp: () => ipcRenderer.send('minimize-app'),
  maximizeApp: () => ipcRenderer.send('maximize-app'),
  pickVideoFromDownloads: () => ipcRenderer.invoke('pick-video-from-downloads'),
  onServerReady: (cb) => ipcRenderer.on('server-ready', cb),
});

