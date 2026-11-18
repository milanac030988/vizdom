import clsx from 'clsx'
import {
  CheckCircle2,
  Copy,
  FlaskConical,
  MousePointer2,
  MousePointerClick,
  Sparkles,
  TriangleAlert,
  XCircle
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { copyText, tryClick } from '../actions'
import { api } from '../api'
import { categoryColor, categoryOf, displayName } from '../lib/elements'
import { selectedElement, useStudio } from '../store'
import type { DomElement, Resolution } from '../types'
import { Badge, Button, EmptyState, Modal, PanelHeader, Spinner } from './ui'

export function Inspector() {
  const el = useStudio(selectedElement)
  return (
    <div className="flex h-full flex-col bg-panel">
      <PanelHeader title="Inspector" />
      <div className="min-h-0 flex-1 overflow-y-auto">
        {el ? (
          <ElementDetails el={el} />
        ) : (
          <EmptyState
            icon={<MousePointer2 size={22} />}
            title="Nothing selected"
            body="Click a box on the screenshot or a row in the list to see its properties and the locator a test would use."
          />
        )}
      </div>
      <LocatorLab />
    </div>
  )
}

function Row({ k, v, mono }: { k: string; v: React.ReactNode; mono?: boolean }) {
  return (
    <div className="grid grid-cols-[96px_1fr] gap-2 py-1">
      <div className="text-muted">{k}</div>
      <div className={clsx('selectable min-w-0 break-words', mono && 'font-mono text-[12px]')}>{v}</div>
    </div>
  )
}

function ElementDetails({ el }: { el: DomElement }) {
  const setLab = useStudio((s) => s.setLab)
  const [x1, y1, x2, y2] = el.bounds
  const c = categoryOf(el)
  const flags = [el.clickable && 'clickable', el.editable && 'editable', el.scrollable && 'scrollable'].filter(Boolean) as string[]
  const alt = Object.entries(el.locators ?? {}).filter(([k]) => k !== 'id')

  return (
    <div className="space-y-4 p-3">
      <div>
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: categoryColor(c) }} />
          <div className="selectable min-w-0 flex-1 truncate text-[15px] font-semibold">{displayName(el)}</div>
          <Badge className="font-mono">{el.id}</Badge>
        </div>
        <div className="mt-1.5 flex flex-wrap gap-1">
          {el.role && <Badge tone="accent">{el.role}</Badge>}
          {el.visual_type && el.visual_type !== el.role && <Badge>{el.visual_type}</Badge>}
          {flags.map((f) => (
            <Badge key={f}>{f}</Badge>
          ))}
        </div>
      </div>

      <div className="rounded-lg border border-line bg-bg">
        <div className="flex items-center justify-between border-b border-line px-3 py-2">
          <div className="text-[12px] font-medium text-muted">Locator (as exported)</div>
          <div className="flex gap-1">
            <Button size="sm" variant="ghost" icon={<FlaskConical size={13} />} onClick={() => setLab(el.locator, null)} title="Open in the Locator Lab">
              Test
            </Button>
            <Button size="sm" variant="ghost" icon={<Copy size={13} />} onClick={() => copyText(el.locator, 'Locator copied')}>
              Copy
            </Button>
          </div>
        </div>
        <div className="selectable break-all px-3 py-2.5 font-mono text-[12px] text-ink">{el.locator}</div>
      </div>

      <ClickButtons locator={el.locator} />

      <div>
        <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted">Properties</div>
        <Row k="Text" v={el.text || <span className="text-faint">—</span>} />
        <Row k="Label" v={el.label || <span className="text-faint">—</span>} />
        {el.hint ? <Row k="Hint" v={String(el.hint)} /> : null}
        <Row k="Bounds" v={`${x1}, ${y1} → ${x2}, ${y2}`} mono />
        <Row k="Size" v={`${x2 - x1} × ${y2 - y1}`} mono />
        {el.center && <Row k="Center" v={`${el.center[0]}, ${el.center[1]}`} mono />}
        {typeof el.confidence === 'number' && (
          <Row
            k="Confidence"
            v={
              <div className="flex items-center gap-2">
                <div className="h-1.5 w-24 overflow-hidden rounded-full bg-raised">
                  <div className="h-full rounded-full bg-accent" style={{ width: `${Math.round(el.confidence * 100)}%` }} />
                </div>
                <span className="font-mono text-[12px]">{el.confidence.toFixed(2)}</span>
              </div>
            }
          />
        )}
      </div>

      {alt.length > 0 && (
        <div>
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted">Other locators</div>
          {alt.map(([k, v]) => (
            <div key={k} className="group flex items-center gap-2 py-0.5">
              <div className="w-[88px] shrink-0 text-muted">{k}</div>
              <code className="selectable min-w-0 flex-1 truncate font-mono text-[12px]">{v}</code>
              <button className="text-faint opacity-0 hover:text-ink group-hover:opacity-100" title="Test in the Locator Lab" onClick={() => setLab(v, null)}>
                <FlaskConical size={13} />
              </button>
              <button className="text-faint opacity-0 hover:text-ink group-hover:opacity-100" title="Copy" onClick={() => copyText(v, 'Locator copied')}>
                <Copy size={13} />
              </button>
            </div>
          ))}
        </div>
      )}

      <AllFields el={el} />
    </div>
  )
}

function fieldValue(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'string') return v === '' ? '""' : v
  return JSON.stringify(v)
}

/** Every key the DOM carries for this element, as the JSON has it. */
function AllFields({ el }: { el: DomElement }) {
  const [open, setOpen] = useState(false)
  const keys = Object.keys(el).sort()
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <button
          className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-muted hover:text-ink"
          onClick={() => setOpen(!open)}
        >
          <span className="inline-block w-3">{open ? '▾' : '▸'}</span> All fields ({keys.length})
        </button>
        {open && (
          <Button size="sm" variant="ghost" icon={<Copy size={13} />} onClick={() => copyText(JSON.stringify(el, null, 2), 'Element JSON copied')}>
            Copy JSON
          </Button>
        )}
      </div>
      {open &&
        keys.map((k) => (
          <div key={k} className="grid grid-cols-[96px_1fr] gap-2 py-0.5">
            <div className="truncate text-muted" title={k}>{k}</div>
            <code className="selectable min-w-0 break-all font-mono text-[12px]">{fieldValue(el[k])}</code>
          </div>
        ))}
    </div>
  )
}

export function ClickButtons({ locator }: { locator: string }) {
  const confirmed = useStudio((s) => s.actuationConfirmed)
  const target = useStudio((s) => s.targetWindow || s.session?.info.window_title || '')
  const job = useStudio((s) => s.job)
  const [pending, setPending] = useState<null | 'single' | 'double' | 'right'>(null)
  const running = job?.state === 'running'

  const go = (kind: 'single' | 'double' | 'right') => {
    if (!confirmed) return setPending(kind)
    tryClick(locator, kind)
  }

  return (
    <>
      <div className="flex gap-1.5">
        <Button className="flex-1 justify-center" icon={<MousePointerClick size={14} />} disabled={running} onClick={() => go('single')} title="Capture again, resolve this locator as the suite would, then click it">
          Try click
        </Button>
        <Button disabled={running} onClick={() => go('double')}>
          Double
        </Button>
        <Button disabled={running} onClick={() => go('right')}>
          Right
        </Button>
      </div>
      <Modal
        open={pending !== null}
        onClose={() => setPending(null)}
        title="Send a real click?"
        width={480}
        footer={
          <>
            <Button variant="ghost" onClick={() => setPending(null)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={!target}
              onClick={() => {
                useStudio.getState().confirmActuation()
                const kind = pending!
                setPending(null)
                tryClick(locator, kind)
              }}
            >
              Click it
            </Button>
          </>
        }
      >
        <div className="space-y-3 p-4">
          <p>
            Studio captures <b>{target || 'the target window'}</b> again, resolves the locator on that fresh screen exactly
            as a Robot test would, raises the window and clicks through the configured actuator.
          </p>
          <code className="selectable block break-all rounded-md bg-bg px-3 py-2 font-mono text-[12px]">{locator}</code>
          {!target && (
            <p className="flex items-center gap-2 text-warn">
              <TriangleAlert size={14} /> Choose a target window in the toolbar first.
            </p>
          )}
          <p className="text-muted">You won't be asked again until Studio restarts.</p>
        </div>
      </Modal>
    </>
  )
}

function LocatorLab() {
  const session = useStudio((s) => s.session)
  const lab = useStudio((s) => s.lab)
  const { setLab, select } = useStudio.getState()
  const [text, setText] = useState(lab.locator)
  const [busy, setBusy] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout>>()
  const seq = useRef(0)

  // An outside "Test" fills the field.
  useEffect(() => {
    if (lab.locator !== text) {
      setText(lab.locator)
      run(lab.locator, false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lab.locator])

  useEffect(() => {
    setText('')
  }, [session?.id])

  const needsModel = /(^|\s|\|\|)desc=/.test(text)

  async function run(locator: string, allowModels: boolean) {
    const s = useStudio.getState().session
    if (!s || !locator.trim()) {
      setLab(locator, null)
      return
    }
    const my = ++seq.current
    setBusy(true)
    try {
      const r = await api.resolve(s.id, locator, allowModels)
      if (my === seq.current) {
        setLab(locator, r)
        if (r.ok && r.element_id) select(r.element_id)
      }
    } catch (e) {
      if (my === seq.current)
        setLab(locator, { ok: false, element_id: null, error: (e as Error).message, alternatives: [] })
    } finally {
      if (my === seq.current) setBusy(false)
    }
  }

  const onChange = (v: string) => {
    setText(v)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => run(v, false), 250)
  }

  return (
    <div className="shrink-0 border-t border-line">
      <div className="flex h-10 items-center gap-2 px-3">
        <FlaskConical size={14} className="text-accent" />
        <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Locator Lab</div>
        {busy && <Spinner className="ml-auto text-muted" />}
      </div>
      <div className="space-y-2 px-3 pb-3">
        <textarea
          value={text}
          onChange={(e) => onChange(e.target.value)}
          disabled={!session}
          spellCheck={false}
          rows={2}
          placeholder={'text=Save role=button || id=E7\ndesc="the save button"'}
          className="no-drag w-full resize-none rounded-md border border-line bg-bg px-2.5 py-2 font-mono text-[12px] outline-none placeholder:text-faint focus:border-accent focus:ring-2 focus:ring-accent/20"
        />
        {needsModel && (
          <Button size="sm" icon={<Sparkles size={13} />} disabled={busy} onClick={() => run(text, true)} className="w-full justify-center">
            Resolve with the grounding models (desc=)
          </Button>
        )}
        <LabResult r={lab.locator === text ? lab.result : null} />
        {lab.result?.ok && lab.locator === text && <ClickButtons locator={text} />}
      </div>
    </div>
  )
}

function LabResult({ r }: { r: Resolution | null }) {
  const select = useStudio((s) => s.select)
  if (!r) return <div className="text-[12px] text-faint">Type a locator: it is resolved live against this screen, as a suite would.</div>
  if (r.ok)
    return (
      <div className="rounded-md border border-ok/30 bg-ok/10 px-3 py-2 text-[12px]">
        <div className="flex items-center gap-2 font-medium text-ok">
          <CheckCircle2 size={14} /> Exactly one element:
          <button className="font-mono underline-offset-2 hover:underline" onClick={() => select(r.element_id)}>
            {r.element_id}
          </button>
        </div>
        {r.used_fallback && (
          <div className="mt-1 text-warn">
            Resolved by alternative #{(r.alternative ?? 0) + 1}: the primary part did not match, it may be stale.
          </div>
        )}
      </div>
    )
  const ambiguous = r.alternatives.some((a) => a.matches.length > 1)
  return (
    <div className={clsx('rounded-md border px-3 py-2 text-[12px]', ambiguous ? 'border-warn/30 bg-warn/10' : 'border-bad/30 bg-bad/10')}>
      <div className={clsx('flex items-center gap-2 font-medium', ambiguous ? 'text-warn' : 'text-bad')}>
        {ambiguous ? <TriangleAlert size={14} /> : <XCircle size={14} />}
        {ambiguous ? 'Ambiguous: a test would fail' : 'Does not resolve'}
      </div>
      {r.alternatives.length > 0 ? (
        <div className="mt-1.5 space-y-1">
          {r.alternatives.map((a, i) => (
            <div key={i} className="flex items-start gap-2">
              <span className="mt-[1px] text-faint">#{i + 1}</span>
              <code className="min-w-0 flex-1 break-all font-mono">{a.rendered}</code>
              <span className="shrink-0 text-muted">
                {a.uses_model ? 'model' : a.matches.length === 0 ? 'no match' : `${a.matches.length} matches`}
              </span>
            </div>
          ))}
          {ambiguous && <div className="text-muted">Matches are outlined in amber. Add text=, role= or hint= to narrow it down.</div>}
        </div>
      ) : (
        <div className="mt-1 text-muted">{r.error}</div>
      )}
    </div>
  )
}
