/** Shapes shared by the main process, the preload script and the renderer. */

export interface BridgeInfo {
  state: 'starting' | 'ready' | 'failed'
  url: string | null
  token: string | null
  python: string
  repo: string
  error: string | null
  log: string[]
}

export interface StudioPrefs {
  pythonPath: string
  theme: 'dark' | 'light' | 'system'
  /** session config the bridge starts with; empty = <repo>/vizdom.config.json */
  configPath: string
}

export interface StudioApi {
  bridge(): Promise<BridgeInfo>
  restartBridge(pythonPath?: string): Promise<BridgeInfo>
  onBridge(cb: (info: BridgeInfo) => void): () => void
  prefs(): Promise<StudioPrefs>
  setPrefs(p: Partial<StudioPrefs>): Promise<StudioPrefs>
  openImage(): Promise<string | null>
  openDom(): Promise<string | null>
  pickPython(): Promise<string | null>
  openConfig(): Promise<string | null>
  saveConfigAs(defaultPath: string): Promise<string | null>
  saveResource(defaultName: string): Promise<string | null>
  hideForCapture(): Promise<void>
  showAfterCapture(): Promise<void>
  revealPath(path: string): Promise<void>
  setTitleBarTheme(dark: boolean): Promise<void>
}
