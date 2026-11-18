import clsx from 'clsx'
import { Maximize, Minus, Plus, Tag } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { CATEGORIES, categoryColor, categoryOf, displayName, hitTest, type Category } from '../lib/elements'
import { useStudio } from '../store'
import type { DomElement } from '../types'
import { IconButton } from './ui'

interface View {
  x: number
  y: number
  k: number
}

const MIN_K = 0.05
const MAX_K = 8

export function Canvas() {
  const session = useStudio((s) => s.session)
  const selectedId = useStudio((s) => s.selectedId)
  const hoverId = useStudio((s) => s.hoverId)
  const lab = useStudio((s) => s.lab)
  const showLabels = useStudio((s) => s.showLabels)
  const fitTick = useStudio((s) => s.fitTick)
  const { select, hover, toggleLabels } = useStudio.getState()

  const wrap = useRef<HTMLDivElement>(null)
  const [view, setView] = useState<View>({ x: 0, y: 0, k: 1 })
  const [hidden, setHidden] = useState<Set<Category>>(new Set(['container']))
  const [tip, setTip] = useState<{ x: number; y: number; e: DomElement } | null>(null)
  const drag = useRef<{ sx: number; sy: number; vx: number; vy: number; moved: boolean } | null>(null)

  const width = session?.image.width || 1
  const height = session?.image.height || 1

  const elements = useMemo(() => session?.elements ?? [], [session])
  const cats = useMemo(() => new Map(elements.map((e) => [e.id, categoryOf(e)])), [elements])
  const visible = useMemo(() => elements.filter((e) => !hidden.has(cats.get(e.id)!)), [elements, hidden, cats])

  const labMatches = useMemo(() => {
    const r = lab.result
    if (!r) return new Set<string>()
    if (r.ok && r.element_id) return new Set([r.element_id])
    return new Set(r.alternatives.flatMap((a) => a.matches))
  }, [lab.result])
  const labOk = Boolean(lab.result?.ok)

  const fit = useCallback(() => {
    const el = wrap.current
    if (!el || !session) return
    // room at the bottom for the legend and the zoom bar
    const pad = 28
    const bottom = 64
    const k = Math.min((el.clientWidth - pad * 2) / width, (el.clientHeight - pad - bottom) / height, 2)
    setView({ k, x: (el.clientWidth - width * k) / 2, y: pad + (el.clientHeight - pad - bottom - height * k) / 2 })
  }, [session, width, height])

  useEffect(() => {
    fit()
  }, [fitTick, fit])

  useEffect(() => {
    const el = wrap.current
    if (!el) return
    const ro = new ResizeObserver(() => fit())
    ro.observe(el)
    return () => ro.disconnect()
  }, [fit])

  const zoomAt = useCallback((factor: number, cx?: number, cy?: number) => {
    setView((v) => {
      const el = wrap.current
      const px = cx ?? (el ? el.clientWidth / 2 : 0)
      const py = cy ?? (el ? el.clientHeight / 2 : 0)
      const k = Math.min(MAX_K, Math.max(MIN_K, v.k * factor))
      const f = k / v.k
      return { k, x: px - (px - v.x) * f, y: py - (py - v.y) * f }
    })
  }, [])

  // Keyboard zoom, scoped to the inspect view being visible.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || (e.target as HTMLElement)?.tagName === 'INPUT') return
      if (e.key === '0') (e.preventDefault(), fit())
      else if (e.key === '=' || e.key === '+') (e.preventDefault(), zoomAt(1.25))
      else if (e.key === '-') (e.preventDefault(), zoomAt(0.8))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [fit, zoomAt])

  // Bring the selection into view when it is chosen elsewhere (tree, lab).
  useEffect(() => {
    const el = wrap.current
    const e = elements.find((x) => x.id === selectedId)
    if (!el || !e) return
    const [x1, y1, x2, y2] = e.bounds
    setView((v) => {
      const sx1 = v.x + x1 * v.k
      const sy1 = v.y + y1 * v.k
      const sx2 = v.x + x2 * v.k
      const sy2 = v.y + y2 * v.k
      if (sx1 >= 0 && sy1 >= 0 && sx2 <= el.clientWidth && sy2 <= el.clientHeight) return v
      const cx = ((x1 + x2) / 2) * v.k
      const cy = ((y1 + y2) / 2) * v.k
      return { ...v, x: el.clientWidth / 2 - cx, y: el.clientHeight / 2 - cy }
    })
  }, [selectedId, elements])

  const toImage = (clientX: number, clientY: number) => {
    const r = wrap.current!.getBoundingClientRect()
    return { x: (clientX - r.left - view.x) / view.k, y: (clientY - r.top - view.y) / view.k, lx: clientX - r.left, ly: clientY - r.top }
  }

  const onWheel = (e: React.WheelEvent) => {
    const r = wrap.current!.getBoundingClientRect()
    zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top)
  }

  const onDown = (e: React.MouseEvent) => {
    if (e.button !== 0 && e.button !== 1) return
    drag.current = { sx: e.clientX, sy: e.clientY, vx: view.x, vy: view.y, moved: false }
  }

  const onMove = (e: React.MouseEvent) => {
    const d = drag.current
    if (d) {
      const dx = e.clientX - d.sx
      const dy = e.clientY - d.sy
      if (d.moved || Math.abs(dx) + Math.abs(dy) > 4) {
        d.moved = true
        setView((v) => ({ ...v, x: d.vx + dx, y: d.vy + dy }))
        setTip(null)
        return
      }
    }
    if (!session) return
    const p = toImage(e.clientX, e.clientY)
    const hit = hitTest(visible, p.x, p.y)
    if ((hit?.id ?? null) !== useStudio.getState().hoverId) hover(hit?.id ?? null)
    setTip(hit ? { x: p.lx, y: p.ly, e: hit } : null)
  }

  const onUp = (e: React.MouseEvent) => {
    const d = drag.current
    drag.current = null
    if (!d || d.moved || e.button !== 0 || !session) return
    const p = toImage(e.clientX, e.clientY)
    select(hitTest(visible, p.x, p.y)?.id ?? null)
  }

  const onLeave = () => {
    drag.current = null
    hover(null)
    setTip(null)
  }

  if (!session) return null
  const stroke = 1.5 / view.k

  return (
    <div className="relative h-full w-full overflow-hidden checker">
      <div
        ref={wrap}
        className={clsx('absolute inset-0', drag.current?.moved ? 'cursor-grabbing' : 'cursor-crosshair')}
        onWheel={onWheel}
        onMouseDown={onDown}
        onMouseMove={onMove}
        onMouseUp={onUp}
        onMouseLeave={onLeave}
        onDoubleClick={() => fit()}
      >
        <div
          className="absolute left-0 top-0 origin-top-left"
          style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.k})`, width, height }}
        >
          {session.has_screenshot ? (
            <img
              src={api.screenshotUrl(session.id)}
              width={width}
              height={height}
              draggable={false}
              className="block shadow-pop"
              style={{ imageRendering: view.k > 2 ? 'pixelated' : 'auto' }}
            />
          ) : (
            <div className="h-full w-full bg-panel" />
          )}
          <svg className="absolute inset-0" width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
            {visible.map((e) => {
              const [x1, y1, x2, y2] = e.bounds
              const c = cats.get(e.id)!
              const sel = e.id === selectedId
              const hov = e.id === hoverId
              const inLab = labMatches.has(e.id)
              if (sel || inLab) return null
              return (
                <rect
                  key={e.id}
                  x={x1}
                  y={y1}
                  width={x2 - x1}
                  height={y2 - y1}
                  rx={2 / view.k}
                  fill={categoryColor(c, hov ? 0.18 : 0.04)}
                  stroke={categoryColor(c, hov ? 1 : 0.55)}
                  strokeWidth={hov ? stroke * 1.6 : stroke}
                />
              )
            })}
            {elements
              .filter((e) => labMatches.has(e.id) && e.id !== selectedId)
              .map((e) => {
                const [x1, y1, x2, y2] = e.bounds
                const color = labOk ? 'rgb(var(--ok))' : 'rgb(var(--warn))'
                return (
                  <rect
                    key={`lab-${e.id}`}
                    x={x1}
                    y={y1}
                    width={x2 - x1}
                    height={y2 - y1}
                    rx={2 / view.k}
                    fill={labOk ? 'rgb(var(--ok) / 0.15)' : 'rgb(var(--warn) / 0.15)'}
                    stroke={color}
                    strokeWidth={stroke * 2}
                    strokeDasharray={labOk ? undefined : `${6 / view.k} ${4 / view.k}`}
                  />
                )
              })}
            {elements
              .filter((e) => e.id === selectedId)
              .map((e) => {
                const [x1, y1, x2, y2] = e.bounds
                return (
                  <g key="sel">
                    <rect
                      x={x1 - 3 / view.k}
                      y={y1 - 3 / view.k}
                      width={x2 - x1 + 6 / view.k}
                      height={y2 - y1 + 6 / view.k}
                      rx={4 / view.k}
                      fill="none"
                      stroke="rgb(var(--accent) / 0.35)"
                      strokeWidth={6 / view.k}
                    />
                    <rect
                      x={x1}
                      y={y1}
                      width={x2 - x1}
                      height={y2 - y1}
                      rx={2 / view.k}
                      fill="rgb(var(--accent) / 0.12)"
                      stroke="rgb(var(--accent))"
                      strokeWidth={stroke * 1.6}
                    />
                  </g>
                )
              })}
            {showLabels &&
              visible.map((e) => {
                const [x1, y1] = e.bounds
                const fs = 10 / view.k
                return (
                  <g key={`l-${e.id}`} transform={`translate(${x1}, ${y1 - fs * 1.35})`}>
                    <rect width={fs * (e.id.length * 0.62 + 0.8)} height={fs * 1.3} rx={2 / view.k} fill={categoryColor(cats.get(e.id)!, 0.9)} />
                    <text x={fs * 0.4} y={fs * 0.98} fontSize={fs} fontFamily="Cascadia Code, Consolas, monospace" fill="#fff">
                      {e.id}
                    </text>
                  </g>
                )
              })}
          </svg>
        </div>
      </div>

      {tip && !drag.current?.moved && (
        <div
          className="pointer-events-none absolute z-10 max-w-[320px] rounded-md border border-line bg-panel/95 px-2.5 py-1.5 shadow-pop backdrop-blur"
          style={{ left: tip.x + 14, top: tip.y + 14 }}
        >
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full" style={{ background: categoryColor(cats.get(tip.e.id)!) }} />
            <span className="truncate font-medium">{displayName(tip.e)}</span>
          </div>
          <div className="mt-0.5 font-mono text-[11px] text-muted">
            {tip.e.id} · {tip.e.role || tip.e.visual_type}
          </div>
        </div>
      )}

      {/* bottom-left: legend that doubles as a filter */}
      <div className="absolute bottom-3 left-3 flex items-center gap-1 rounded-lg border border-line bg-panel/90 p-1 shadow-pop backdrop-blur">
        {CATEGORIES.map((c) => {
          const off = hidden.has(c.key)
          const n = elements.filter((e) => cats.get(e.id) === c.key).length
          return (
            <button
              key={c.key}
              onClick={() => {
                const h = new Set(hidden)
                if (off) h.delete(c.key)
                else h.add(c.key)
                setHidden(h)
              }}
              title={off ? `Show ${c.label}` : `Hide ${c.label}`}
              className={clsx(
                'flex h-6 items-center gap-1.5 rounded px-2 text-[11px] transition-opacity hover:bg-raised',
                off && 'opacity-40'
              )}
            >
              <span className="h-2 w-2 rounded-sm" style={{ background: categoryColor(c.key) }} />
              {c.label}
              <span className="text-faint">{n}</span>
            </button>
          )
        })}
      </div>

      {/* bottom-right: zoom */}
      <div className="absolute bottom-3 right-3 flex items-center gap-0.5 rounded-lg border border-line bg-panel/90 p-1 shadow-pop backdrop-blur">
        <IconButton label="Show element ids" active={showLabels} onClick={toggleLabels}>
          <Tag size={15} />
        </IconButton>
        <div className="mx-1 h-5 w-px bg-line" />
        <IconButton label="Zoom out (Ctrl -)" onClick={() => zoomAt(0.8)}>
          <Minus size={15} />
        </IconButton>
        <button className="w-12 text-center font-mono text-[11px] text-muted hover:text-ink" title="Actual size" onClick={() => setView((v) => ({ ...v, k: 1 }))}>
          {Math.round(view.k * 100)}%
        </button>
        <IconButton label="Zoom in (Ctrl +)" onClick={() => zoomAt(1.25)}>
          <Plus size={15} />
        </IconButton>
        <IconButton label="Fit to view (Ctrl 0)" onClick={fit}>
          <Maximize size={15} />
        </IconButton>
      </div>
    </div>
  )
}
