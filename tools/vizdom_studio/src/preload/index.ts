import { contextBridge, ipcRenderer } from 'electron'
import type { BridgeInfo, StudioApi, StudioPrefs } from '../shared/types'

const api: StudioApi = {
  bridge: () => ipcRenderer.invoke('bridge:get'),
  restartBridge: (python?: string) => ipcRenderer.invoke('bridge:restart', python),
  onBridge: (cb) => {
    const handler = (_e: unknown, info: BridgeInfo): void => cb(info)
    ipcRenderer.on('bridge:changed', handler)
    return () => ipcRenderer.removeListener('bridge:changed', handler)
  },
  prefs: () => ipcRenderer.invoke('prefs:get'),
  setPrefs: (p: Partial<StudioPrefs>) => ipcRenderer.invoke('prefs:set', p),
  openImage: () => ipcRenderer.invoke('dialog:openImage'),
  openDom: () => ipcRenderer.invoke('dialog:openDom'),
  pickPython: () => ipcRenderer.invoke('dialog:pickPython'),
  openConfig: () => ipcRenderer.invoke('dialog:openConfig'),
  saveConfigAs: (p: string) => ipcRenderer.invoke('dialog:saveConfigAs', p),
  saveResource: (name: string) => ipcRenderer.invoke('dialog:saveResource', name),
  hideForCapture: () => ipcRenderer.invoke('window:hideForCapture'),
  showAfterCapture: () => ipcRenderer.invoke('window:showAfterCapture'),
  revealPath: (p: string) => ipcRenderer.invoke('shell:reveal', p),
  setTitleBarTheme: (dark: boolean) => ipcRenderer.invoke('window:titleBarTheme', dark)
}

contextBridge.exposeInMainWorld('studio', api)
