import type { DomElement } from '../types'

export type Category = 'button' | 'input' | 'text' | 'icon' | 'container'

export const CATEGORIES: { key: Category; label: string }[] = [
  { key: 'button', label: 'Controls' },
  { key: 'input', label: 'Inputs' },
  { key: 'text', label: 'Text' },
  { key: 'icon', label: 'Icons' },
  { key: 'container', label: 'Containers' }
]

const INPUT = /input|edit|textfield|combo|search|spin|slider/i
const BUTTON = /button|check|radio|toggle|switch|tab|menu|link|item/i
const ICON = /icon|image|symbol|glyph/i
const CONTAINER = /container|group|panel|pane|window|list|tree|toolbar|root/i

/** One of five colours on the canvas, from the DOM's role and visual type. */
export function categoryOf(e: DomElement): Category {
  const kind = `${e.visual_type ?? ''} ${e.role ?? ''}`
  if (INPUT.test(kind) || e.editable) return 'input'
  if (ICON.test(kind)) return 'icon'
  if (BUTTON.test(kind) || e.clickable) return 'button'
  if (CONTAINER.test(kind)) return 'container'
  return 'text'
}

export const categoryVar: Record<Category, string> = {
  button: '--c-button',
  input: '--c-input',
  text: '--c-text',
  icon: '--c-icon',
  container: '--c-container'
}

export function categoryColor(c: Category, alpha = 1): string {
  return `rgb(var(${categoryVar[c]}) / ${alpha})`
}

/** What a person would call the element: its printed text, else its hint, else its role. */
export function displayName(e: DomElement): string {
  const t = (e.text || e.label || e.hint || '').toString().trim()
  return t || `(${e.visual_type || e.role || 'element'})`
}

export function hasCaption(e: DomElement): boolean {
  return Boolean((e.text || e.label || e.hint || '').toString().trim())
}

export function matchesQuery(e: DomElement, q: string): boolean {
  if (!q) return true
  const hay = `${e.id} ${e.text ?? ''} ${e.label ?? ''} ${e.hint ?? ''} ${e.role ?? ''} ${e.visual_type ?? ''} ${e.locator}`.toLowerCase()
  return q
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((w) => hay.includes(w))
}

export function area(e: DomElement): number {
  const [x1, y1, x2, y2] = e.bounds
  return Math.max(0, x2 - x1) * Math.max(0, y2 - y1)
}

/** The smallest element under a point: what a click on overlapping boxes means. */
export function hitTest(elements: DomElement[], x: number, y: number): DomElement | null {
  let best: DomElement | null = null
  for (const e of elements) {
    const [x1, y1, x2, y2] = e.bounds
    if (x >= x1 && x <= x2 && y >= y1 && y <= y2 && (!best || area(e) < area(best))) best = e
  }
  return best
}

export function relativeTime(iso?: string): string {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const s = Math.round((Date.now() - t) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  const d = Math.round(s / 86400)
  if (d < 14) return `${d} d ago`
  return new Date(t).toLocaleDateString()
}

export function sessionDate(id: string): string {
  const m = /^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/.exec(id)
  if (!m) return id
  return `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}`
}
