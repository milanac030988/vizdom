/** Navigation rail, job progress, toasts, status bar. */
import clsx from 'clsx'
import { CheckCircle2, Info, LayoutGrid, Moon, ScanSearch, Server, Settings2, Sun, X, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useStudio, type View } from '../store'
import { Spinner } from './ui'

const NAV: { view: View; label: string; icon: React.ReactNode; kbd: string }[] = [
  { view: 'inspect', label: 'Inspect', icon: <ScanSearch size={19} />, kbd: 'Ctrl 1' },
  { view: 'sessions', label: 'Sessions', icon: <LayoutGrid size={19} />, kbd: 'Ctrl 2' },
  { view: 'services', label: 'Services', icon: <Server size={19} />, kbd: 'Ctrl 3' },
  { view: 'settings', label: 'Settings', icon: <Settings2 size={19} />, kbd: 'Ctrl ,' }
]

export function NavRail() {
  const view = useStudio((s) => s.view)
  const dark = useStudio((s) => s.dark)
  const { setView, setDark } = useStudio.getState()
  return (
    <nav className="flex w-14 shrink-0 flex-col items-center gap-1 border-r border-line bg-panel py-2">
      {NAV.map((n) => (
        <button
          key={n.view}
          onClick={() => setView(n.view)}
          title={`${n.label} (${n.kbd})`}
          className={clsx(
            'relative flex h-11 w-11 flex-col items-center justify-center gap-0.5 rounded-lg transition-colors',
            view === n.view ? 'bg-accent/15 text-accent' : 'text-muted hover:bg-raised hover:text-ink'
          )}
        >
          {view === n.view && <span className="absolute -left-2 h-5 w-[3px] rounded-r bg-accent" />}
          {n.icon}
          <span className="text-[9px] font-medium">{n.label}</span>
        </button>
      ))}
      <div className="flex-1" />
      <button
        onClick={() => {
          setDark(!dark)
          window.studio.setPrefs({ theme: dark ? 'light' : 'dark' })
        }}
        title={dark ? 'Light theme' : 'Dark theme'}
        className="flex h-10 w-10 items-center justify-center rounded-lg text-muted hover:bg-raised hover:text-ink"
      >
        {dark ? <Sun size={17} /> : <Moon size={17} />}
      </button>
    </nav>
  )
}

const STAGES: Record<string, string> = {
  queued: 'Queued',
  models: 'Loading models',
  analyze: 'Analysing',
  save: 'Saving',
  capture: 'Capturing',
  click: 'Clicking'
}

/** A thin progress line under the title bar plus a card with the current stage. */
export function JobProgress() {
  const job = useStudio((s) => s.job)
  const [now, setNow] = useState(Date.now())
  const [started] = useState(() => new Map<string, number>())
  const running = job?.state === 'running'
  useEffect(() => {
    if (!running) return
    const t = setInterval(() => setNow(Date.now()), 500)
    return () => clearInterval(t)
  }, [running])
  if (!job || !running) return null
  if (!started.has(job.id)) started.set(job.id, Date.now())
  const secs = Math.max(0, Math.round((now - started.get(job.id)!) / 1000))
  return (
    <>
      <div className="pointer-events-none absolute inset-x-0 top-0 z-30 h-0.5 overflow-hidden bg-accent/20">
        <div className="h-full bg-accent transition-[width] duration-500" style={{ width: `${Math.max(job.progress, 6)}%` }} />
      </div>
      <div className="absolute left-1/2 top-4 z-30 flex -translate-x-1/2 items-center gap-3 rounded-full border border-line bg-panel/95 py-1.5 pl-3 pr-4 shadow-pop backdrop-blur animate-slide-in">
        <Spinner className="text-accent" />
        <div className="text-[12px]">
          <span className="font-medium">{STAGES[job.stage] ?? job.stage}</span>
          {job.message && <span className="text-muted"> · {job.message}</span>}
        </div>
        <span className="font-mono text-[11px] text-faint">{secs}s</span>
      </div>
    </>
  )
}

export function Toasts() {
  const toasts = useStudio((s) => s.toasts)
  const dismiss = useStudio((s) => s.dismiss)
  return (
    <div className="pointer-events-none fixed bottom-10 right-4 z-[60] flex w-[360px] flex-col gap-2">
      {toasts.map((t) => (
        <div key={t.id} className="pointer-events-auto flex gap-3 rounded-lg border border-line bg-panel p-3 shadow-pop animate-slide-in">
          <span className={clsx('mt-0.5', t.kind === 'ok' ? 'text-ok' : t.kind === 'error' ? 'text-bad' : 'text-accent')}>
            {t.kind === 'ok' ? <CheckCircle2 size={16} /> : t.kind === 'error' ? <XCircle size={16} /> : <Info size={16} />}
          </span>
          <div className="min-w-0 flex-1">
            <div className="font-medium">{t.title}</div>
            {t.body && <div className="selectable mt-0.5 break-words text-[12px] text-muted">{t.body}</div>}
            {t.action && (
              <button className="mt-1.5 text-[12px] font-medium text-accent hover:underline" onClick={t.action.run}>
                {t.action.label}
              </button>
            )}
          </div>
          <button onClick={() => dismiss(t.id)} className="self-start text-faint hover:text-ink">
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  )
}

export function StatusBar({ connected }: { connected: boolean }) {
  const session = useStudio((s) => s.session)
  const selectedId = useStudio((s) => s.selectedId)
  const marked = useStudio((s) => s.marked)
  const info = session?.info
  return (
    <footer className="flex h-7 shrink-0 items-center gap-4 border-t border-line bg-panel px-3 text-[11px] text-muted">
      <span className="flex items-center gap-1.5">
        <span className={clsx('h-1.5 w-1.5 rounded-full', connected ? 'bg-ok' : 'bg-bad')} />
        {connected ? 'Bridge connected' : 'Bridge reconnecting…'}
      </span>
      {session && (
        <>
          <span className="font-mono">{session.id}</span>
          <span>
            {session.image.width}×{session.image.height}
          </span>
          <span>{session.elements.length} elements</span>
          {info?.window_title && <span className="truncate">{String(info.window_title)}</span>}
          {info?.detector && (
            <span>
              {String(info.detector)} · {String(info.ocr_engine ?? '')}
              {info.analysis_seconds ? ` · ${info.analysis_seconds}s` : ''}
            </span>
          )}
        </>
      )}
      <span className="flex-1" />
      {marked.size > 0 && <span className="text-accent">{marked.size} marked for export</span>}
      {selectedId && <span className="font-mono">selected {selectedId}</span>}
    </footer>
  )
}
