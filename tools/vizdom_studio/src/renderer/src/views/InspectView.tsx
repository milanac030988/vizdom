import { Camera, FileJson, FileUp, ScanSearch } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels'
import { captureAndAnalyze, openDom, openImage } from '../actions'
import { api } from '../api'
import { Canvas } from '../components/Canvas'
import { ElementsPanel } from '../components/ElementsPanel'
import { Inspector } from '../components/Inspector'
import { Button, Kbd, Spinner } from '../components/ui'
import { relativeTime, sessionDate } from '../lib/elements'
import { useStudio } from '../store'
import type { SessionSummary } from '../types'

function Handle() {
  return <PanelResizeHandle className="w-px bg-line transition-colors data-[resize-handle-state=drag]:bg-accent data-[resize-handle-state=hover]:bg-accent/60" />
}

export function InspectView() {
  const session = useStudio((s) => s.session)
  const loading = useStudio((s) => s.loadingSession)
  if (!session) return loading ? <div className="flex h-full items-center justify-center"><Spinner className="text-muted" /></div> : <Welcome />
  return (
    <PanelGroup direction="horizontal" autoSaveId="vizdom-inspect">
      <Panel defaultSize={22} minSize={14}>
        <ElementsPanel />
      </Panel>
      <Handle />
      <Panel defaultSize={52} minSize={30}>
        <Canvas />
      </Panel>
      <Handle />
      <Panel defaultSize={26} minSize={18}>
        <Inspector />
      </Panel>
    </PanelGroup>
  )
}

function Welcome() {
  const target = useStudio((s) => s.targetWindow)
  const [recent, setRecent] = useState<SessionSummary[] | null>(null)
  useEffect(() => {
    api.sessions().then((l) => setRecent(l.slice(0, 6)), () => setRecent([]))
  }, [])

  return (
    <div className="flex h-full items-center justify-center overflow-auto p-10">
      <div className="w-full max-w-3xl">
        <div className="mb-8 flex items-center gap-4">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-accent/15 text-accent">
            <ScanSearch size={28} />
          </div>
          <div>
            <h1 className="text-[22px] font-semibold tracking-tight">Turn a screen into a testable DOM</h1>
            <p className="text-muted">Capture an application, inspect what VizDOM sees, prove a locator, export it to Robot Framework.</p>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <Card
            icon={<Camera size={18} />}
            title="Capture & Analyze"
            body={target ? `Grab “${target}” and analyse it.` : 'Grab the full screen, or pick a window in the toolbar first.'}
            kbd="F5"
            onClick={captureAndAnalyze}
            primary
          />
          <Card icon={<FileUp size={18} />} title="Analyze an image" body="A screenshot or a camera photo from disk." kbd="Ctrl O" onClick={openImage} />
          <Card icon={<FileJson size={18} />} title="Open a Visual DOM" body="A dom_result.json from the Viewer, a suite or a benchmark." kbd="Ctrl D" onClick={openDom} />
        </div>

        <div className="mt-10">
          <div className="mb-3 flex items-center">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Recent sessions</div>
            <Button size="sm" variant="ghost" className="ml-auto" onClick={() => useStudio.getState().setView('sessions')}>
              See all
            </Button>
          </div>
          {recent === null ? (
            <Spinner className="text-muted" />
          ) : recent.length === 0 ? (
            <div className="rounded-lg border border-dashed border-line p-6 text-center text-muted">No sessions yet. Your first capture lands here.</div>
          ) : (
            <div className="grid grid-cols-3 gap-3">
              {recent.map((r) => (
                <SessionCard key={r.id} s={r} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function Card({ icon, title, body, kbd, onClick, primary }: { icon: React.ReactNode; title: string; body: string; kbd: string; onClick: () => void; primary?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={
        'group flex flex-col items-start gap-2 rounded-xl border p-4 text-left transition-all hover:-translate-y-0.5 hover:shadow-pop ' +
        (primary ? 'border-accent/50 bg-accent/10' : 'border-line bg-panel')
      }
    >
      <div className="flex w-full items-center">
        <span className={primary ? 'text-accent' : 'text-muted group-hover:text-ink'}>{icon}</span>
        <Kbd className="ml-auto">{kbd}</Kbd>
      </div>
      <div className="font-semibold">{title}</div>
      <div className="text-[12px] text-muted">{body}</div>
    </button>
  )
}

export function SessionCard({ s }: { s: SessionSummary }) {
  return (
    <button
      onClick={() => useStudio.getState().openSession(s.id)}
      className="group overflow-hidden rounded-xl border border-line bg-panel text-left transition-all hover:-translate-y-0.5 hover:border-accent/50 hover:shadow-pop"
    >
      <div className="checker flex aspect-[16/10] items-center justify-center overflow-hidden border-b border-line">
        {s.has_screenshot ? (
          <img src={api.screenshotUrl(s.id)} loading="lazy" className="max-h-full max-w-full object-contain" />
        ) : (
          <FileJson className="text-faint" />
        )}
      </div>
      <div className="p-3">
        <div className="truncate font-medium">{s.window_title || (s.capture_source === 'file' ? 'Image file' : 'Screen')}</div>
        <div className="mt-0.5 flex items-center gap-2 text-[12px] text-muted">
          <span title={sessionDate(s.id)}>{relativeTime(s.timestamp) || sessionDate(s.id)}</span>
          <span>·</span>
          <span>{s.element_count ?? '?'} elements</span>
          {s.detector && <span className="ml-auto font-mono text-[11px] text-faint">{s.detector}</span>}
        </div>
      </div>
    </button>
  )
}
