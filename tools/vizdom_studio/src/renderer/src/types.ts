export interface DomElement {
  id: string
  bounds: [number, number, number, number]
  center?: [number, number]
  role?: string
  visual_type?: string
  clickable?: boolean
  editable?: boolean
  scrollable?: boolean
  confidence?: number
  text?: string
  label?: string
  hint?: string
  locators?: Record<string, string>
  /** the locator the Robot exporter writes for this element */
  locator: string
  [key: string]: unknown
}

export interface Outline {
  id: string
  children: Outline[]
}

export interface SessionInfo {
  session_id?: string
  timestamp?: string
  window_title?: string
  capture_source?: string
  capture_scope?: string
  detector?: string
  ocr_engine?: string
  analysis_seconds?: number
  element_count?: number
  source_file?: string
  [key: string]: unknown
}

export interface SessionView {
  id: string
  info: SessionInfo
  image: { width: number; height: number }
  has_screenshot: boolean
  elements: DomElement[]
  hierarchy: Outline | null
}

export interface SessionSummary {
  id: string
  timestamp?: string
  element_count?: number
  window_title?: string
  capture_source?: string
  detector?: string
  ocr_engine?: string
  width?: number
  height?: number
  has_screenshot: boolean
}

export interface Job {
  id: string
  kind: 'analyze' | 'try'
  state: 'running' | 'done' | 'error'
  title: string
  stage: string
  progress: number
  message: string
  result: Record<string, unknown> | null
  error: string | null
  elapsed?: number
}

export interface Resolution {
  ok: boolean
  element_id: string | null
  alternative?: number | null
  rendered?: string | null
  used_fallback?: boolean
  attempts?: { rendered: string; why: string }[]
  error: string | null
  alternatives: { rendered: string; matches: string[]; uses_model: boolean }[]
  seconds?: number
}

export interface ConfigPayload {
  path: string
  exists: boolean
  config: Record<string, Record<string, unknown>>
  summary: { detector: string; ocr: string; refiner: string | null; capture: string; tiers: string[] }
}

export interface Strategy {
  name: string
  platform: string
  description: string
  available: boolean
}

export interface ServiceOption {
  name: string
  label: string
  type: 'select' | 'text' | 'number' | 'bool' | 'lines'
  flag: string
  default: unknown
  choices?: [string, string][]
  help?: string
  placeholder?: string
  when?: Record<string, string[]>
  advanced?: boolean
  invert?: boolean
}

export type ServiceValues = Record<string, string | boolean | number | null>

export interface ServiceStatus {
  options: ServiceOption[]
  values: ServiceValues
  running_values: ServiceValues | null
  command: string[]
  key: string
  title: string
  module: string
  port: number
  default_port: number
  hint: string
  state: 'running' | 'starting' | 'external' | 'stopped'
  ready: boolean
  detail: string
  owned: boolean
  log: string[]
}
