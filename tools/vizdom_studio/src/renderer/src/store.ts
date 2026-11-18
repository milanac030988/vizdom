import { create } from 'zustand'
import { api, ApiError } from './api'
import type { ConfigPayload, Job, Resolution, SessionView } from './types'

export type View = 'inspect' | 'sessions' | 'services' | 'settings'

export interface Toast {
  id: number
  kind: 'info' | 'ok' | 'error'
  title: string
  body?: string
  action?: { label: string; run: () => void }
}

interface State {
  view: View
  dark: boolean
  session: SessionView | null
  loadingSession: boolean
  selectedId: string | null
  hoverId: string | null
  /** what the Locator Lab currently resolves to, drawn on the canvas */
  lab: { locator: string; result: Resolution | null }
  marked: Set<string>
  job: Job | null
  targetWindow: string
  windows: string[]
  config: ConfigPayload | null
  toasts: Toast[]
  paletteOpen: boolean
  exportOpen: boolean
  showLabels: boolean
  /** bumped to ask the canvas to fit / zoom */
  fitTick: number
  focusSearchTick: number
  actuationConfirmed: boolean

  setView(v: View): void
  setDark(d: boolean): void
  openSession(id: string, select?: string | null): Promise<void>
  select(id: string | null): void
  hover(id: string | null): void
  setLab(locator: string, result: Resolution | null): void
  toggleMark(id: string): void
  setMarked(ids: string[]): void
  setJob(j: Job | null): void
  setTarget(t: string): void
  refreshWindows(): Promise<void>
  refreshConfig(): Promise<void>
  setConfig(c: ConfigPayload): void
  toast(t: Omit<Toast, 'id'>): void
  dismiss(id: number): void
  setPalette(o: boolean): void
  setExport(o: boolean): void
  toggleLabels(): void
  fit(): void
  focusSearch(): void
  confirmActuation(): void
}

let toastId = 1

export const useStudio = create<State>((set, get) => ({
  view: 'inspect',
  dark: true,
  session: null,
  loadingSession: false,
  selectedId: null,
  hoverId: null,
  lab: { locator: '', result: null },
  marked: new Set(),
  job: null,
  targetWindow: '',
  windows: [],
  config: null,
  toasts: [],
  paletteOpen: false,
  exportOpen: false,
  showLabels: false,
  fitTick: 0,
  focusSearchTick: 0,
  actuationConfirmed: false,

  setView: (view) => set({ view }),
  setDark: (dark) => {
    document.documentElement.classList.toggle('dark', dark)
    window.studio?.setTitleBarTheme(dark)
    set({ dark })
  },
  openSession: async (id, select = null) => {
    set({ loadingSession: true })
    try {
      const session = await api.session(id)
      set({
        session,
        selectedId: select,
        hoverId: null,
        marked: new Set(),
        lab: { locator: '', result: null },
        view: 'inspect',
        fitTick: get().fitTick + 1
      })
      const title = session.info.window_title
      if (title && !get().targetWindow && session.info.capture_scope === 'window') set({ targetWindow: title })
    } catch (e) {
      get().toast({ kind: 'error', title: 'Could not open the session', body: (e as Error).message })
    } finally {
      set({ loadingSession: false })
    }
  },
  select: (selectedId) => set({ selectedId }),
  hover: (hoverId) => set({ hoverId }),
  setLab: (locator, result) => set({ lab: { locator, result } }),
  toggleMark: (id) => {
    const marked = new Set(get().marked)
    if (marked.has(id)) marked.delete(id)
    else marked.add(id)
    set({ marked })
  },
  setMarked: (ids) => set({ marked: new Set(ids) }),
  setJob: (job) => set({ job }),
  setTarget: (targetWindow) => set({ targetWindow }),
  refreshWindows: async () => {
    try {
      set({ windows: await api.windows() })
    } catch {
      /* listing windows is best effort */
    }
  },
  refreshConfig: async () => {
    try {
      set({ config: await api.config() })
    } catch (e) {
      if (!(e instanceof ApiError)) throw e
    }
  },
  setConfig: (config) => set({ config }),
  toast: (t) => {
    const id = toastId++
    set({ toasts: [...get().toasts, { ...t, id }].slice(-4) })
    setTimeout(() => get().dismiss(id), t.kind === 'error' ? 9000 : 4500)
  },
  dismiss: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
  setPalette: (paletteOpen) => set({ paletteOpen }),
  setExport: (exportOpen) => set({ exportOpen }),
  toggleLabels: () => set({ showLabels: !get().showLabels }),
  fit: () => set({ fitTick: get().fitTick + 1 }),
  focusSearch: () => set({ focusSearchTick: get().focusSearchTick + 1, view: 'inspect' }),
  confirmActuation: () => set({ actuationConfirmed: true })
}))

export const selectedElement = (s: State) =>
  s.session && s.selectedId ? (s.session.elements.find((e) => e.id === s.selectedId) ?? null) : null
