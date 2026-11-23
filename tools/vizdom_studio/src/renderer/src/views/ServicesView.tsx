import clsx from 'clsx'
import {
  ArrowDownToLine,
  ChevronRight,
  Copy,
  Cpu,
  Eraser,
  FileJson,
  Link2,
  MonitorSmartphone,
  MousePointerClick,
  Play,
  RotateCw,
  Search,
  Square,
  Terminal,
  WrapText
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { copyText } from '../actions'
import { api } from '../api'
import { Badge, Button, Input, Select, Spinner, Switch } from '../components/ui'
import { useStudio } from '../store'
import type { ServiceOption, ServiceStatus, ServiceValues } from '../types'

const ICONS: Record<string, React.ReactNode> = {
  detector: <Cpu size={18} />,
  capture: <MonitorSmartphone size={18} />,
  actuator: <MousePointerClick size={18} />
}

const USE_LABEL: Record<string, string> = {
  detector: 'Analyze with this detector',
  capture: 'Capture through this service',
  actuator: 'Click through this service'
}

/** Live service logs arrive as bridge events; the view polls health every 4 s. */
export const serviceLogBus = new EventTarget()

export function ServicesView() {
  const [list, setList] = useState<ServiceStatus[] | null>(null)

  const load = () => api.services().then(setList, () => undefined)
  useEffect(() => {
    load()
    const t = setInterval(load, 4000)
    const onChange = () => load()
    serviceLogBus.addEventListener('changed', onChange)
    return () => {
      clearInterval(t)
      serviceLogBus.removeEventListener('changed', onChange)
    }
  }, [])

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-line bg-panel px-6 py-4">
        <h2 className="text-[16px] font-semibold">Services</h2>
        <p className="max-w-4xl text-[12px] text-muted">
          Optional. Studio analyses in-process by default. Run a service to keep one warm model for several tools, or to capture and
          click on another machine. Options are remembered; services started here stop when Studio closes, and ones started elsewhere
          show as external and are left alone.
        </p>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-6">
        {!list ? (
          <Spinner className="text-muted" />
        ) : (
          <div className="mx-auto flex max-w-6xl flex-col gap-4">
            {list.map((s) => (
              <ServiceCard key={s.key} s={s} onList={setList} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function visible(o: ServiceOption, v: ServiceValues): boolean {
  return !o.when || Object.entries(o.when).every(([k, allowed]) => allowed.includes(String(v[k] ?? '')))
}

function commandFor(s: ServiceStatus, port: string, v: ServiceValues): string {
  const parts = ['python', '-m', s.module, '--port', port || String(s.default_port)]
  for (const o of s.options) {
    if (!visible(o, v)) continue
    const val = v[o.name] ?? o.default
    if (o.type === 'bool') {
      if (o.invert ? !val : Boolean(val)) parts.push(o.flag)
    } else if (o.type === 'lines') {
      String(val ?? '')
        .split('\n')
        .map((l) => l.trim())
        .filter(Boolean)
        .forEach((l) => parts.push(o.flag, l))
    } else if (val !== '' && val !== null && val !== undefined) {
      parts.push(o.flag, /\s/.test(String(val)) ? `"${val}"` : String(val))
    }
  }
  return parts.join(' ')
}

function ServiceCard({ s, onList }: { s: ServiceStatus; onList: (l: ServiceStatus[]) => void }) {
  const toast = useStudio((st) => st.toast)
  const setConfig = useStudio((st) => st.setConfig)
  const config = useStudio((st) => st.config)
  const [values, setValues] = useState<ServiceValues>(s.values)
  const [port, setPort] = useState(String(s.port))
  const [advanced, setAdvanced] = useState(false)
  const [busy, setBusy] = useState(false)
  const save = useRef<ReturnType<typeof setTimeout>>()

  const running = s.owned
  const locked = running || s.state === 'external'
  const command = useMemo(() => (running ? s.command.join(' ') : commandFor(s, port, values)), [running, s, port, values])
  const changedWhileRunning =
    running && s.running_values && JSON.stringify(normal(values, s)) !== JSON.stringify(normal(s.running_values, s))

  // Remember the form (debounced) so the next launch starts from it.
  const remember = (v: ServiceValues, p: string) => {
    clearTimeout(save.current)
    save.current = setTimeout(() => api.saveServiceOptions(s.key, Number(p) || s.default_port, v).catch(() => undefined), 500)
  }
  const setValue = (name: string, val: ServiceValues[string]) => {
    const v = { ...values, [name]: val }
    setValues(v)
    remember(v, port)
  }

  const run = async (fn: () => Promise<ServiceStatus[]>, what: string) => {
    setBusy(true)
    try {
      onList(await fn())
    } catch (e) {
      toast({ kind: 'error', title: what, body: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }
  const start = () => run(() => api.startService(s.key, Number(port) || s.default_port, values), `Could not start ${s.title}`)
  const stop = () => run(() => api.stopService(s.key), `Could not stop ${s.title}`)
  const restart = async () => {
    await run(() => api.stopService(s.key), `Could not stop ${s.title}`)
    await start()
  }
  const inUse = isInUse(s.key, s.port, config?.config)
  const use = async () => {
    try {
      setConfig(await api.useService(s.key, s.port))
      toast({
        kind: 'ok',
        title: USE_LABEL[s.key],
        body: `localhost:${s.port} is now used for the next analysis. Save it in Settings to keep it.`
      })
    } catch (e) {
      toast({ kind: 'error', title: 'Could not switch to the service', body: (e as Error).message })
    }
  }

  const tone = s.state === 'running' ? 'ok' : s.state === 'starting' ? 'warn' : s.state === 'external' ? 'accent' : 'neutral'
  const opts = s.options.filter((o) => visible(o, values))
  const basic = opts.filter((o) => !o.advanced)
  const extra = opts.filter((o) => o.advanced)

  return (
    <div className="overflow-hidden rounded-xl border border-line bg-panel">
      <div className="flex items-center gap-3 border-b border-line px-4 py-3">
        <div className={clsx('flex h-10 w-10 items-center justify-center rounded-lg', s.ready ? 'bg-ok/15 text-ok' : 'bg-raised text-muted')}>
          {ICONS[s.key]}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[14px] font-semibold">{s.title}</span>
            <Badge tone={tone}>
              {s.state === 'starting' && <Spinner className="h-2.5 w-2.5" />}
              {s.state}
            </Badge>
            {s.ready && <span className="font-mono text-[11px] text-faint">localhost:{s.port} · {s.detail}</span>}
            {inUse && <Badge tone="accent">used for analysis</Badge>}
          </div>
          <div className="text-[12px] text-muted">{s.hint}</div>
        </div>
        <div className="flex items-center gap-2">
          {s.ready && !inUse && (
            <Button icon={<Link2 size={13} />} onClick={use} title="Point the session config at this service">
              {USE_LABEL[s.key]}
            </Button>
          )}
          {running ? (
            <>
              {changedWhileRunning && (
                <Button icon={<RotateCw size={13} />} disabled={busy} onClick={restart} title="Stop and start again with the new options">
                  Restart to apply
                </Button>
              )}
              <Button variant="danger" icon={<Square size={13} />} disabled={busy} onClick={stop}>
                Stop
              </Button>
            </>
          ) : (
            <Button variant="primary" icon={busy ? <Spinner /> : <Play size={13} />} disabled={busy || s.state === 'external'} onClick={start}>
              Start
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-[minmax(340px,1fr)_minmax(0,1.15fr)]">
        <div className="border-r border-line p-4">
          <div className="space-y-3">
            <OptionRow label="Port" help="The service listens on all interfaces at this port.">
              <Input
                value={port}
                disabled={locked}
                onChange={(e) => {
                  const p = e.target.value.replace(/\D/g, '')
                  setPort(p)
                  remember(values, p)
                }}
                className="w-28"
              />
            </OptionRow>
            {basic.map((o) => (
              <OptionField key={o.name} o={o} value={values[o.name]} onChange={(v) => setValue(o.name, v)} disabled={s.state === 'external'} />
            ))}
            {extra.length > 0 && (
              <button onClick={() => setAdvanced(!advanced)} className="flex items-center gap-1 text-[12px] text-muted hover:text-ink">
                <ChevronRight size={13} className={clsx('transition-transform', advanced && 'rotate-90')} />
                Advanced ({extra.length})
              </button>
            )}
            {advanced &&
              extra.map((o) => (
                <OptionField key={o.name} o={o} value={values[o.name]} onChange={(v) => setValue(o.name, v)} disabled={s.state === 'external'} />
              ))}
          </div>
          {config && s.state !== 'external' && (
            <button
              onClick={() => {
                const v = { ...values, ...fromConfig(s.key, config.config) }
                setValues(v)
                remember(v, port)
                toast({ kind: 'info', title: `${s.title}: options taken from the config`, body: config.path })
              }}
              title={`Fill these options from ${config.path}`}
              className="mt-3 flex items-center gap-1.5 text-[12px] text-accent hover:underline"
            >
              <FileJson size={13} /> Fill from the session config ({config.path.split(/[\\/]/).pop()})
            </button>
          )}
          {s.state === 'external' && (
            <p className="mt-3 text-[12px] text-muted">Started outside Studio: its options are whatever it was launched with.</p>
          )}
          {changedWhileRunning && <p className="mt-3 text-[12px] text-warn">Options changed: restart the service to apply them.</p>}
          <div className="mt-4 rounded-md border border-line bg-bg">
            <div className="flex items-center justify-between px-3 pt-2 text-[11px] font-semibold uppercase tracking-wider text-muted">
              {running ? 'Running as' : 'Will run'}
              <button title="Copy the command" className="text-faint hover:text-ink" onClick={() => copyText(command, 'Command copied')}>
                <Copy size={12} />
              </button>
            </div>
            <code className="selectable block break-all px-3 pb-2.5 pt-1 font-mono text-[11px] text-ink">{command}</code>
          </div>
        </div>
        <ServiceLog s={s} onList={onList} />
      </div>
    </div>
  )
}

/**
 * The service options the session config implies. A config whose detector or
 * capture is itself `grpc` says nothing about how the service should run, so
 * those keys are left alone.
 */
function fromConfig(key: string, cfg: Record<string, Record<string, unknown>>): ServiceValues {
  const s = (v: unknown) => (v === null || v === undefined ? '' : String(v))
  if (key === 'detector') {
    const d = cfg.detector ?? {}
    const out: ServiceValues = {
      gpu: Boolean(d.use_gpu),
      ocr: s(cfg.ocr?.engine),
      box_threshold: s(d.omniparser_box_threshold),
      contour_pass: Boolean(d.contour_pass),
      icon_library: s(d.icon_library),
      yolo_model: s(d.yolo_model_path),
      icon_detect: s(d.omniparser_icon_detect_path),
      icon_caption: s(d.omniparser_icon_caption_path)
    }
    if (['uied', 'yolo', 'omniparser', 'modular'].includes(String(d.backend))) out.backend = String(d.backend)
    return out
  }
  const section = cfg[key] ?? {}
  const out: ServiceValues = {
    window_title: s(section.window_title || (key === 'actuator' ? cfg.capture?.window_title : ''))
  }
  if (section.strategy !== 'grpc') out.strategy = s(section.strategy)
  return out
}

function normal(v: ServiceValues, s: ServiceStatus): ServiceValues {
  const out: ServiceValues = {}
  for (const o of s.options) if (visible(o, v)) out[o.name] = (v[o.name] ?? o.default ?? '') as ServiceValues[string]
  return out
}

function isInUse(key: string, port: number, cfg?: Record<string, Record<string, unknown>>): boolean {
  if (!cfg) return false
  const target = `localhost:${port}`
  if (key === 'detector') return cfg.detector?.backend === 'grpc' && cfg.detector?.grpc_target === target
  const section = cfg[key]
  return section?.strategy === 'grpc' && section?.target === target
}

function OptionRow({ label, help, children }: { label: string; help?: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[150px_1fr] items-start gap-3">
      <div className="pt-1.5">
        <div className="font-medium">{label}</div>
        {help && <div className="mt-0.5 text-[11px] leading-snug text-muted">{help}</div>}
      </div>
      <div className="flex min-h-8 items-center">{children}</div>
    </div>
  )
}

function OptionField({
  o,
  value,
  onChange,
  disabled
}: {
  o: ServiceOption
  value: ServiceValues[string] | undefined
  onChange: (v: ServiceValues[string]) => void
  disabled?: boolean
}) {
  const v = value ?? (o.default as ServiceValues[string]) ?? ''
  let control: React.ReactNode
  if (o.type === 'select')
    control = (
      <Select
        value={String(v ?? '')}
        onChange={onChange}
        className="w-full"
        options={(o.choices ?? []).map(([value, label]) => ({ value, label }))}
      />
    )
  else if (o.type === 'bool') control = <Switch checked={Boolean(v)} onChange={onChange} label={o.label} />
  else if (o.type === 'lines')
    control = (
      <textarea
        value={String(v ?? '')}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        rows={3}
        placeholder={o.placeholder}
        className="w-full rounded-md border border-line bg-bg px-2.5 py-1.5 font-mono text-[12px] outline-none placeholder:text-faint focus:border-accent"
      />
    )
  else
    control = (
      <Input
        value={String(v ?? '')}
        onChange={(e) => onChange(e.target.value)}
        placeholder={o.placeholder}
        disabled={disabled}
        inputMode={o.type === 'number' ? 'decimal' : undefined}
        className="w-full"
      />
    )
  return (
    <OptionRow label={o.label} help={o.help}>
      <div className={clsx('w-full', disabled && 'pointer-events-none opacity-50')}>{control}</div>
    </OptionRow>
  )
}

type Level = 'all' | 'warn' | 'error'

const ERROR_RE = /\b(ERROR|CRITICAL|FATAL)\b|Traceback|Exception|Error:|\[exited with code [1-9]/
const WARN_RE = /\bWARN(ING)?\b/

function levelOf(line: string): 'error' | 'warn' | 'cmd' | 'info' {
  if (ERROR_RE.test(line)) return 'error'
  if (WARN_RE.test(line)) return 'warn'
  if (line.startsWith('$ ')) return 'cmd'
  return 'info'
}

/**
 * The service's console. It takes exactly the height of the options column
 * beside it (absolute fill), so a chatty service scrolls inside the box instead
 * of stretching the card; long lines wrap by default, or scroll sideways.
 */
function ServiceLog({ s, onList }: { s: ServiceStatus; onList: (l: ServiceStatus[]) => void }) {
  const toast = useStudio((st) => st.toast)
  const [log, setLog] = useState<string[]>(s.log)
  const [query, setQuery] = useState('')
  const [level, setLevel] = useState<Level>('all')
  const [wrap, setWrap] = useState(true)
  const [follow, setFollow] = useState(true)
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => setLog(s.log), [s.log])
  useEffect(() => {
    const onLine = (e: Event) => {
      const d = (e as CustomEvent).detail as { key: string; line: string }
      if (d.key === s.key) setLog((l) => [...l, d.line].slice(-400))
    }
    serviceLogBus.addEventListener('line', onLine)
    return () => serviceLogBus.removeEventListener('line', onLine)
  }, [s.key])

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return log
      .map((text) => ({ text, kind: levelOf(text) }))
      .filter((l) => (level === 'all' ? true : level === 'error' ? l.kind === 'error' : l.kind === 'error' || l.kind === 'warn'))
      .filter((l) => !q || l.text.toLowerCase().includes(q))
  }, [log, query, level])
  const counts = useMemo(() => {
    let warn = 0
    let error = 0
    for (const l of log) {
      const k = levelOf(l)
      if (k === 'error') error++
      else if (k === 'warn') warn++
    }
    return { warn, error }
  }, [log])

  // Stay on the newest line while following; scrolling up pauses that.
  useEffect(() => {
    const el = boxRef.current
    if (el && follow) el.scrollTop = el.scrollHeight
  }, [shown, follow])
  const onScroll = () => {
    const el = boxRef.current
    if (!el) return
    const atEnd = el.scrollHeight - el.scrollTop - el.clientHeight < 24
    if (atEnd !== follow) setFollow(atEnd)
  }

  const clear = async () => {
    setLog([])
    try {
      onList(await api.clearServiceLog(s.key))
    } catch (e) {
      toast({ kind: 'error', title: `Could not clear the ${s.title} log`, body: (e as Error).message })
    }
  }
  const filtered = query.trim() !== '' || level !== 'all'

  return (
    <div className="relative min-h-[300px] min-w-0 bg-bg">
      <div className="absolute inset-0 flex min-w-0 flex-col">
        <div className="flex items-center gap-1.5 border-b border-line px-3 py-2">
          <span className="mr-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">
            <Terminal size={12} /> Output
          </span>
          <div className="relative min-w-0 flex-1">
            <Search size={12} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-faint" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Escape' && setQuery('')}
              placeholder="Filter lines"
              className="h-7 w-full rounded-md border border-line bg-panel pl-7 pr-2 text-[12px] outline-none placeholder:text-faint focus:border-accent"
            />
          </div>
          <div className="flex shrink-0 overflow-hidden rounded-md border border-line text-[11px]">
            {(
              [
                ['all', 'All', null],
                ['warn', 'Warn', counts.warn + counts.error],
                ['error', 'Errors', counts.error]
              ] as [Level, string, number | null][]
            ).map(([k, label, n]) => (
              <button
                key={k}
                onClick={() => setLevel(k)}
                title={k === 'all' ? 'Every line' : k === 'warn' ? 'Warnings and errors' : 'Errors only'}
                className={clsx(
                  'flex h-7 items-center gap-1 px-2',
                  level === k ? 'bg-raised text-ink' : 'text-muted hover:text-ink',
                  k !== 'all' && 'border-l border-line'
                )}
              >
                {label}
                {n !== null && n > 0 && (
                  <span className={clsx('font-mono', k === 'error' || counts.error ? 'text-bad' : 'text-warn')}>{n}</span>
                )}
              </button>
            ))}
          </div>
          <LogTool title={wrap ? 'Wrap long lines: on' : 'Wrap long lines: off (scroll sideways)'} active={wrap} onClick={() => setWrap(!wrap)}>
            <WrapText size={13} />
          </LogTool>
          <LogTool
            title="Copy the lines shown"
            onClick={() => copyText(shown.map((l) => l.text).join('\n'), `${shown.length} lines copied`)}
            disabled={!shown.length}
          >
            <Copy size={13} />
          </LogTool>
          <LogTool title="Clear the output" onClick={clear} disabled={!log.length}>
            <Eraser size={13} />
          </LogTool>
        </div>

        <div
          ref={boxRef}
          onScroll={onScroll}
          className={clsx(
            'selectable min-h-0 flex-1 overflow-y-auto px-3 py-2 font-mono text-[11px] leading-relaxed',
            wrap ? 'overflow-x-hidden' : 'overflow-x-auto'
          )}
        >
          {!log.length ? (
            <div className="text-faint">No output yet. Start the service to see its log here.</div>
          ) : !shown.length ? (
            <div className="text-faint">No line matches the filter.</div>
          ) : (
            <div className={wrap ? '' : 'w-max min-w-full'}>
              {shown.map((l, i) => (
                <div
                  key={i}
                  className={clsx(
                    wrap ? 'whitespace-pre-wrap break-words [overflow-wrap:anywhere]' : 'whitespace-pre',
                    l.kind === 'error' ? 'text-bad' : l.kind === 'warn' ? 'text-warn' : l.kind === 'cmd' ? 'text-accent' : 'text-muted'
                  )}
                >
                  {l.text || ' '}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex h-7 shrink-0 items-center justify-between border-t border-line px-3 text-[11px] text-faint">
          <span>{filtered ? `${shown.length} of ${log.length} lines` : `${log.length} lines`}</span>
          {!follow && (
            <button
              onClick={() => setFollow(true)}
              className="flex items-center gap-1 text-accent hover:underline"
              title="Scroll to the newest line and keep following"
            >
              <ArrowDownToLine size={12} /> Jump to latest
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

function LogTool({
  title,
  active,
  disabled,
  onClick,
  children
}: {
  title: string
  active?: boolean
  disabled?: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      title={title}
      aria-label={title}
      aria-pressed={active}
      disabled={disabled}
      onClick={onClick}
      className={clsx(
        'flex h-7 w-7 shrink-0 items-center justify-center rounded-md border',
        active ? 'border-accent/50 bg-accent/10 text-accent' : 'border-transparent text-muted hover:bg-raised hover:text-ink',
        'disabled:pointer-events-none disabled:opacity-40'
      )}
    >
      {children}
    </button>
  )
}
