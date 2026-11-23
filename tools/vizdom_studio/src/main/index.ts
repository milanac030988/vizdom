import { app, BrowserWindow, dialog, ipcMain, nativeTheme, shell } from 'electron'
import { existsSync, readFileSync, writeFileSync } from 'fs'
import { join } from 'path'
import { Bridge, bundledPython, dataHome } from './bridge'
import type { StudioPrefs } from '../shared/types'

const prefsFile = (): string => join(app.getPath('userData'), 'prefs.json')

function loadPrefs(): StudioPrefs {
  const bundled = bundledPython()
  const defaults: StudioPrefs = {
    // the installed Studio brings its own interpreter; a checkout uses the one on PATH
    pythonPath: process.env.VIZDOM_PYTHON || bundled || 'python',
    theme: 'dark',
    configPath: process.env.VIZDOM_CONFIG || ''
  }
  let p: StudioPrefs
  try {
    p = { ...defaults, ...JSON.parse(readFileSync(prefsFile(), 'utf8')) }
  } catch {
    p = defaults
  }
  // a bare "python" (the old default) or an interpreter that is gone yields to the bundled one
  if (bundled && !process.env.VIZDOM_PYTHON && (p.pythonPath === 'python' || !existsSync(p.pythonPath))) {
    p.pythonPath = bundled
  }
  return p
}

function savePrefs(p: StudioPrefs): void {
  try {
    writeFileSync(prefsFile(), JSON.stringify(p, null, 2))
  } catch {
    /* prefs are a convenience */
  }
}

let prefs: StudioPrefs
let win: BrowserWindow | null = null
let bridge: Bridge
let quitting = false

const OVERLAY = {
  dark: { color: '#0d1117', symbolColor: '#c9d1d9', height: 44 },
  light: { color: '#f6f8fa', symbolColor: '#24292f', height: 44 }
}

// The VizDOM icon (written by tools/assets/make_app_icon.py); out/main -> ../../resources.
// Windows takes the window/taskbar icon from the .ico, other platforms from the PNG.
function appIcon(): string | undefined {
  const file = join(__dirname, '../../resources', process.platform === 'win32' ? 'icon.ico' : 'icon.png')
  return existsSync(file) ? file : undefined
}

function createWindow(): void {
  const dark = prefs.theme === 'dark' || (prefs.theme === 'system' && nativeTheme.shouldUseDarkColors)
  win = new BrowserWindow({
    width: 1480,
    height: 920,
    minWidth: 1040,
    minHeight: 640,
    icon: appIcon(),
    show: false,
    backgroundColor: dark ? '#0d1117' : '#f6f8fa',
    title: 'VizDOM Studio',
    titleBarStyle: 'hidden',
    titleBarOverlay: process.platform === 'darwin' ? undefined : dark ? OVERLAY.dark : OVERLAY.light,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false
    }
  })
  win.once('ready-to-show', () => win?.show())
  // Never stay invisible: if the page does not report ready, show it anyway
  // (a blank or broken page is something the user can see and report).
  const fallback = setTimeout(() => win && !win.isVisible() && win.show(), 1500)
  win.once('show', () => clearTimeout(fallback))
  win.webContents.on('did-fail-load', (_e, code, desc, url) =>
    console.error(`[studio] renderer failed to load ${url}: ${code} ${desc}`)
  )
  win.webContents.on('render-process-gone', (_e, d) => console.error(`[studio] renderer gone: ${d.reason} (${d.exitCode})`))
  win.webContents.on('console-message', (_e, level, message, line, source) => {
    if (level >= 2) console.error(`[renderer] ${message} (${source}:${line})`)
  })
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })
  if (process.env.ELECTRON_RENDERER_URL) {
    win.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    win.loadFile(join(__dirname, '../renderer/index.html'))
  }
  // Closing Studio stops the services it started: say so first, and let the
  // user keep working instead (a test suite may still be using them).
  let closeConfirmed = false
  let asking = false
  win.on('close', (e) => {
    if (closeConfirmed || quitting || !bridge) return
    e.preventDefault()
    if (asking) return
    asking = true
    const w = win!
    bridge
      .ownedServices()
      .then(async (running) => {
        if (running.length) {
          const r = await dialog.showMessageBox(w, {
            type: 'warning',
            title: 'Close VizDOM Studio',
            message:
              running.length === 1
                ? 'A service started by Studio is still running.'
                : `${running.length} services started by Studio are still running.`,
            detail:
              running.join('\n') +
              (running.length === 1
                ? '\n\nClosing Studio stops it. Tests and other tools that use it will lose the connection.'
                : '\n\nClosing Studio stops them. Tests and other tools that use them will lose the connection.'),
            buttons: ['Stop and close', 'Cancel'],
            defaultId: 0,
            cancelId: 1,
            noLink: true
          })
          if (r.response !== 0) return
        }
        closeConfirmed = true
        w.close()
      })
      .finally(() => (asking = false))
  })
  win.on('closed', () => (win = null))
}

function registerIpc(): void {
  ipcMain.handle('bridge:get', () => bridge.info)
  ipcMain.handle('bridge:restart', async (_e, python?: string) => {
    if (python) {
      prefs = { ...prefs, pythonPath: python }
      savePrefs(prefs)
    }
    return bridge.start(prefs.pythonPath, prefs.configPath)
  })
  ipcMain.handle('prefs:get', () => prefs)
  ipcMain.handle('prefs:set', (_e, patch: Partial<StudioPrefs>) => {
    prefs = { ...prefs, ...patch }
    savePrefs(prefs)
    return prefs
  })
  ipcMain.handle('dialog:openImage', async () => {
    const r = await dialog.showOpenDialog(win!, {
      title: 'Analyze an image',
      properties: ['openFile'],
      filters: [{ name: 'Images', extensions: ['png', 'jpg', 'jpeg', 'bmp', 'webp'] }]
    })
    return r.canceled ? null : r.filePaths[0]
  })
  ipcMain.handle('dialog:openDom', async () => {
    const sessions = join(dataHome(), 'output', 'sessions')
    const r = await dialog.showOpenDialog(win!, {
      title: 'Open a Visual DOM',
      defaultPath: existsSync(sessions) ? sessions : undefined,
      properties: ['openFile'],
      filters: [{ name: 'Visual DOM JSON', extensions: ['json'] }]
    })
    return r.canceled ? null : r.filePaths[0]
  })
  ipcMain.handle('dialog:pickPython', async () => {
    const r = await dialog.showOpenDialog(win!, {
      title: 'Python interpreter with VizDOM dependencies',
      properties: ['openFile'],
      filters: process.platform === 'win32' ? [{ name: 'Python', extensions: ['exe'] }] : []
    })
    return r.canceled ? null : r.filePaths[0]
  })
  ipcMain.handle('dialog:openConfig', async () => {
    const r = await dialog.showOpenDialog(win!, {
      title: 'Open a VizDOM session config',
      defaultPath: dataHome(),
      properties: ['openFile'],
      filters: [{ name: 'VizDOM config', extensions: ['json'] }]
    })
    return r.canceled ? null : r.filePaths[0]
  })
  ipcMain.handle('dialog:saveConfigAs', async (_e, defaultPath: string) => {
    const r = await dialog.showSaveDialog(win!, {
      title: 'Save the session config as',
      defaultPath: defaultPath || join(dataHome(), 'vizdom.config.json'),
      filters: [{ name: 'VizDOM config', extensions: ['json'] }]
    })
    return r.canceled ? null : r.filePath
  })
  ipcMain.handle('dialog:saveResource', async (_e, defaultName: string) => {
    const r = await dialog.showSaveDialog(win!, {
      title: 'Export Robot Framework resource',
      defaultPath: defaultName,
      filters: [{ name: 'Robot resource', extensions: ['resource', 'robot'] }]
    })
    return r.canceled ? null : r.filePath
  })
  // The capture must not photograph Studio itself: hide, let the window
  // manager repaint what was behind, then grab (the Viewer does the same).
  ipcMain.handle('window:hideForCapture', async () => {
    if (!win) return
    win.hide()
    await new Promise((r) => setTimeout(r, 350))
  })
  ipcMain.handle('window:showAfterCapture', () => {
    if (!win) return
    win.show()
    win.focus()
  })
  ipcMain.handle('shell:reveal', (_e, p: string) => shell.showItemInFolder(p))
  ipcMain.handle('window:titleBarTheme', (_e, dark: boolean) => {
    if (win && process.platform !== 'darwin') win.setTitleBarOverlay(dark ? OVERLAY.dark : OVERLAY.light)
  })
}

process.on('uncaughtException', (e) => console.error('[studio] main process error:', e))

app.whenReady().then(() => {
  console.log('[studio] app ready, creating window')
  app.setAppUserModelId('com.vizdom.studio')
  prefs = loadPrefs()
  bridge = new Bridge(prefs.pythonPath)
  bridge.onChange((info) => win?.webContents.send('bridge:changed', info))
  registerIpc()
  createWindow()
  bridge.start(prefs.pythonPath, prefs.configPath)
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

// Services started from Studio must not outlive it: let the bridge stop them
// before it is ended (a kill on Windows skips the bridge's own cleanup).
app.on('before-quit', (e) => {
  if (quitting || !bridge) return
  e.preventDefault()
  quitting = true
  bridge.shutdown().finally(() => app.quit())
})
