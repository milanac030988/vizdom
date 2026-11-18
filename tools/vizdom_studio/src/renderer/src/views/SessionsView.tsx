import { LayoutGrid, RefreshCw, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { Button, EmptyState, Input, Spinner } from '../components/ui'
import { sessionDate } from '../lib/elements'
import type { SessionSummary } from '../types'
import { SessionCard } from './InspectView'

export function SessionsView() {
  const [all, setAll] = useState<SessionSummary[] | null>(null)
  const [q, setQ] = useState('')
  const load = () => {
    setAll(null)
    api.sessions().then(setAll, () => setAll([]))
  }
  useEffect(load, [])

  const list = useMemo(() => {
    const t = q.toLowerCase()
    return (all ?? []).filter((s) =>
      `${s.id} ${sessionDate(s.id)} ${s.window_title ?? ''} ${s.detector ?? ''} ${s.capture_source ?? ''}`.toLowerCase().includes(t)
    )
  }, [all, q])

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-line bg-panel px-6 py-4">
        <div>
          <h2 className="text-[16px] font-semibold">Sessions</h2>
          <p className="text-[12px] text-muted">Every analysed screen in output/sessions: shared with the PyQt Viewer.</p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search window, date, detector…" icon={<Search size={14} />} className="w-72" />
          <Button icon={<RefreshCw size={14} />} onClick={load}>
            Refresh
          </Button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-6">
        {all === null ? (
          <div className="flex justify-center p-10">
            <Spinner className="text-muted" />
          </div>
        ) : list.length === 0 ? (
          <EmptyState icon={<LayoutGrid size={22} />} title={q ? 'No session matches' : 'No sessions yet'} body={q ? `Nothing for “${q}”.` : 'Capture & Analyze (F5) creates the first one.'} />
        ) : (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-4">
            {list.map((s) => (
              <SessionCard key={s.id} s={s} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
