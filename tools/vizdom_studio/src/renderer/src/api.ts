/** Typed client for the Python bridge (tools/vizdom_bridge). */
import type {
  ConfigPayload,
  Job,
  Resolution,
  ServiceStatus,
  ServiceValues,
  SessionSummary,
  SessionView,
  Strategy
} from './types'

let base = ''
let token = ''

export function configureApi(url: string, tok: string): void {
  base = url
  token = tok
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number
  ) {
    super(message)
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  let r: Response
  try {
    r = await fetch(base + path, {
      method,
      headers: { 'X-VizDOM-Token': token, ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined
    })
  } catch {
    throw new ApiError('The VizDOM bridge is not reachable', 0)
  }
  if (!r.ok) {
    let detail = r.statusText
    try {
      const j = await r.json()
      detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch {
      /* keep statusText */
    }
    throw new ApiError(detail, r.status)
  }
  return r.json() as Promise<T>
}

export const api = {
  screenshotUrl: (id: string) => `${base}/api/sessions/${encodeURIComponent(id)}/screenshot?token=${token}`,
  sessions: () => call<SessionSummary[]>('GET', '/api/sessions'),
  session: (id: string) => call<SessionView>('GET', `/api/sessions/${encodeURIComponent(id)}`),
  windows: () => call<string[]>('GET', '/api/windows'),
  strategies: () =>
    call<{ capture: Strategy[]; capture_default: string | null; actuator: Strategy[] }>('GET', '/api/strategies'),
  capture: (window_title: string | null, strategy?: string | null) =>
    call<Job>('POST', '/api/capture', { window_title, strategy }),
  analyzeFile: (path: string) => call<Job>('POST', '/api/analyze-file', { path }),
  reanalyze: (id: string) => call<Job>('POST', `/api/sessions/${encodeURIComponent(id)}/reanalyze`),
  importDom: (path: string) => call<{ session_id: string }>('POST', '/api/import-dom', { path }),
  resolve: (id: string, locator: string, allow_models = false) =>
    call<Resolution>('POST', `/api/sessions/${encodeURIComponent(id)}/resolve`, { locator, allow_models }),
  exportPreview: (id: string, element_ids: string[] | null, naming: string) =>
    call<{ content: string; path: null; count: number }>('POST', `/api/sessions/${encodeURIComponent(id)}/export`, {
      element_ids,
      naming
    }),
  exportFile: (id: string, element_ids: string[] | null, naming: string, title: string, path: string) =>
    call<{ content: string; path: string; count: number }>('POST', `/api/sessions/${encodeURIComponent(id)}/export`, {
      element_ids,
      naming,
      title,
      path
    }),
  tryLocator: (
    id: string,
    body: { locator: string; click_type: string; window_title: string | null; recapture_before: boolean; recapture_after: boolean }
  ) => call<Job>('POST', `/api/sessions/${encodeURIComponent(id)}/try`, body),
  config: () => call<ConfigPayload>('GET', '/api/config'),
  patchConfig: (changes: Record<string, unknown>) => call<ConfigPayload>('PATCH', '/api/config', changes),
  saveConfig: (path?: string) => call<ConfigPayload>('POST', '/api/config/save', path ? { path } : {}),
  loadConfig: (path: string) => call<ConfigPayload>('POST', '/api/config/load', { path }),
  reloadConfig: () => call<ConfigPayload>('POST', '/api/config/reload'),
  services: () => call<ServiceStatus[]>('GET', '/api/services'),
  startService: (key: string, port: number, values: ServiceValues) =>
    call<ServiceStatus[]>('POST', `/api/services/${key}/start`, { port, values }),
  saveServiceOptions: (key: string, port: number, values: ServiceValues) =>
    call<ServiceStatus[]>('PUT', `/api/services/${key}/options`, { port, values }),
  useService: (key: string, port: number) => call<ConfigPayload>('POST', `/api/services/${key}/use`, { port }),
  stopService: (key: string) => call<ServiceStatus[]>('POST', `/api/services/${key}/stop`),
  clearServiceLog: (key: string) => call<ServiceStatus[]>('DELETE', `/api/services/${key}/log`),
  currentJob: () => call<Job | null>('GET', '/api/jobs/current')
}

export type BridgeEvent =
  | { type: 'job'; job: Job }
  | { type: 'service-log'; key: string; line: string }
  | { type: 'services-changed' }

/** Subscribe to bridge events; reconnects until disposed. */
export function connectEvents(onEvent: (e: BridgeEvent) => void, onState: (open: boolean) => void): () => void {
  let ws: WebSocket | null = null
  let closed = false
  let ping: ReturnType<typeof setInterval> | null = null
  const open = (): void => {
    if (closed) return
    ws = new WebSocket(base.replace(/^http/, 'ws') + `/api/events?token=${token}`)
    ws.onopen = () => {
      onState(true)
      ping = setInterval(() => ws?.readyState === 1 && ws.send('ping'), 20_000)
    }
    ws.onmessage = (m) => {
      try {
        onEvent(JSON.parse(m.data))
      } catch {
        /* ignore malformed */
      }
    }
    ws.onclose = () => {
      onState(false)
      if (ping) clearInterval(ping)
      if (!closed) setTimeout(open, 1500)
    }
  }
  open()
  return () => {
    closed = true
    ws?.close()
  }
}
