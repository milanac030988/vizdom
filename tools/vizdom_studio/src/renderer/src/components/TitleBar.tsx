import clsx from 'clsx'
import { AppWindow, Camera, ChevronDown, FileJson, FileUp, FolderOpen, Monitor, RefreshCw, Search, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { captureAndAnalyze, openDom, openImage, reanalyze } from '../actions'
import { useStudio } from '../store'
import { Button, Kbd } from './ui'

export function TitleBar() {
  const session = useStudio((s) => s.session)
  const job = useStudio((s) => s.job)
  const config = useStudio((s) => s.config)
  const running = job?.state === 'running'

  return (
    <header className="drag flex h-11 shrink-0 items-center gap-2 border-b border-line bg-panel pl-3 pr-[150px]">
      <div className="flex shrink-0 items-center gap-2 pr-2">
        <Logo />
        <span className="hidden whitespace-nowrap text-[13px] font-semibold tracking-tight 2xl:inline">VizDOM Studio</span>
      </div>
      <div className="mx-1 h-5 w-px bg-line" />
      <TargetPicker />
      <Button variant="primary" icon={<Camera size={14} />} kbd="F5" disabled={running} onClick={captureAndAnalyze}>
        Capture &amp; Analyze
      </Button>
      <Button icon={<RefreshCw size={14} />} kbd="F6" disabled={running || !session} onClick={reanalyze} title="Run the pipeline again on this screenshot (after changing a setting)">
        Re-analyze
      </Button>
      <OpenMenu />
      <Button icon={<Upload size={14} />} disabled={!session} onClick={() => useStudio.getState().setExport(true)} kbd="Ctrl E">
        Export
      </Button>

      <div className="flex-1" />

      <button
        onClick={() => useStudio.getState().setPalette(true)}
        title="Command palette (Ctrl K)"
        className="no-drag flex h-8 shrink-0 items-center gap-2 whitespace-nowrap rounded-md border border-line bg-bg px-2.5 text-faint transition-colors hover:border-faint/60 xl:w-56"
      >
        <Search size={14} />
        <span className="hidden flex-1 text-left xl:inline">Search commands…</span>
        <Kbd>Ctrl K</Kbd>
      </button>
      {config && (
        <button
          onClick={() => useStudio.getState().setView('settings')}
          title="Pipeline in use: click to change"
          className="no-drag flex h-8 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-md px-2 font-mono text-[11px] text-muted hover:bg-raised hover:text-ink"
        >
          <span className="h-1.5 w-1.5 rounded-full bg-ok" />
          {config.summary.detector} · {config.summary.ocr}
          {config.summary.refiner ? ` · ${config.summary.refiner}` : ''}
        </button>
      )}
    </header>
  )
}

function Logo() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" className="text-accent">
      <rect x="2.5" y="3.5" width="19" height="17" rx="3" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <rect x="6" y="7.5" width="6" height="4" rx="1" fill="currentColor" />
      <rect x="6" y="13.5" width="12" height="3" rx="1" fill="currentColor" opacity=".45" />
      <rect x="14" y="7.5" width="4" height="4" rx="1" fill="currentColor" opacity=".7" />
    </svg>
  )
}

function useOutside(ref: React.RefObject<HTMLElement>, onOut: () => void, active: boolean) {
  useEffect(() => {
    if (!active) return
    const h = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && onOut()
    window.addEventListener('mousedown', h)
    return () => window.removeEventListener('mousedown', h)
  }, [ref, onOut, active])
}

function TargetPicker() {
  const target = useStudio((s) => s.targetWindow)
  const windows = useStudio((s) => s.windows)
  const { setTarget, refreshWindows } = useStudio.getState()
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const box = useRef<HTMLDivElement>(null)
  useOutside(box, () => setOpen(false), open)

  const list = windows.filter((w) => w.toLowerCase().includes(q.toLowerCase()) && !/VizDOM Studio/.test(w))

  return (
    <div ref={box} className="no-drag relative">
      <button
        onClick={() => {
          setOpen(!open)
          setQ('')
          refreshWindows()
        }}
        className="flex h-8 w-64 items-center gap-2 rounded-md border border-line bg-bg px-2.5 text-left hover:border-faint/60"
        title="What Capture grabs: one application window, or the whole screen"
      >
        {target ? <AppWindow size={14} className="text-accent" /> : <Monitor size={14} className="text-muted" />}
        <span className={clsx('min-w-0 flex-1 truncate', !target && 'text-muted')}>{target || 'Full screen'}</span>
        <ChevronDown size={14} className="text-faint" />
      </button>
      {open && (
        <div className="absolute left-0 top-9 z-40 w-[380px] overflow-hidden rounded-lg border border-line bg-panel shadow-pop animate-slide-in">
          <div className="border-b border-line p-2">
            <input
              autoFocus
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Find a window…"
              className="h-8 w-full rounded-md border border-line bg-bg px-2.5 outline-none focus:border-accent"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && list[0]) {
                  setTarget(list[0])
                  setOpen(false)
                }
                if (e.key === 'Escape') setOpen(false)
              }}
            />
          </div>
          <div className="max-h-80 overflow-y-auto py-1">
            <PickerRow icon={<Monitor size={14} />} label="Full screen" active={!target} onClick={() => (setTarget(''), setOpen(false))} />
            {list.map((w) => (
              <PickerRow key={w} icon={<AppWindow size={14} />} label={w} active={w === target} onClick={() => (setTarget(w), setOpen(false))} />
            ))}
            {list.length === 0 && <div className="px-3 py-4 text-center text-muted">No window matches.</div>}
          </div>
        </div>
      )}
    </div>
  )
}

function PickerRow({ icon, label, active, onClick }: { icon: React.ReactNode; label: string; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} className={clsx('flex h-8 w-full items-center gap-2 px-3 text-left hover:bg-raised', active && 'text-accent')}>
      <span className="text-muted">{icon}</span>
      <span className="truncate">{label}</span>
    </button>
  )
}

function OpenMenu() {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  useOutside(box, () => setOpen(false), open)
  const item = (icon: React.ReactNode, label: string, hint: string, kbd: string, run: () => void) => (
    <button
      onClick={() => {
        setOpen(false)
        run()
      }}
      className="flex w-full items-start gap-3 px-3 py-2 text-left hover:bg-raised"
    >
      <span className="mt-0.5 text-muted">{icon}</span>
      <span className="flex-1">
        <span className="block font-medium">{label}</span>
        <span className="block text-[12px] text-muted">{hint}</span>
      </span>
      <Kbd>{kbd}</Kbd>
    </button>
  )
  return (
    <div ref={box} className="no-drag relative">
      <Button icon={<FolderOpen size={14} />} onClick={() => setOpen(!open)}>
        Open <ChevronDown size={13} className="text-faint" />
      </Button>
      {open && (
        <div className="absolute left-0 top-9 z-40 w-80 overflow-hidden rounded-lg border border-line bg-panel py-1 shadow-pop animate-slide-in">
          {item(<FileUp size={15} />, 'Analyze an image…', 'Run the pipeline on a PNG/JPG from disk', 'Ctrl O', openImage)}
          {item(<FileJson size={15} />, 'Open a Visual DOM…', 'A dom_result.json and the screenshot beside it', 'Ctrl D', openDom)}
          {item(<FolderOpen size={15} />, 'Browse sessions', 'Every capture you analysed before', 'Ctrl 2', () => useStudio.getState().setView('sessions'))}
        </div>
      )}
    </div>
  )
}
