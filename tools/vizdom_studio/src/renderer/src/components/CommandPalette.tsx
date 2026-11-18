import { Command } from 'cmdk'
import {
  Camera,
  Crosshair,
  FileJson,
  FileUp,
  LayoutGrid,
  Maximize,
  Moon,
  RefreshCw,
  ScanSearch,
  Search,
  Server,
  Settings2,
  Tag,
  Upload
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { captureAndAnalyze, openConfig, openDom, openImage, reanalyze } from '../actions'
import { api } from '../api'
import { displayName, sessionDate } from '../lib/elements'
import { useStudio } from '../store'
import type { SessionSummary } from '../types'
import { Kbd } from './ui'

export function CommandPalette() {
  const open = useStudio((s) => s.paletteOpen)
  const session = useStudio((s) => s.session)
  const s = useStudio.getState()
  const [recent, setRecent] = useState<SessionSummary[]>([])
  const [q, setQ] = useState('')

  useEffect(() => {
    if (!open) return
    setQ('')
    api.sessions().then((l) => setRecent(l.slice(0, 8)), () => setRecent([]))
  }, [open])

  if (!open) return null
  const close = () => s.setPalette(false)
  const run = (fn: () => void) => () => {
    close()
    fn()
  }

  const item = (icon: React.ReactNode, label: string, fn: () => void, kbd?: string, value?: string) => (
    <Command.Item value={value ?? label} onSelect={run(fn)} className="flex h-9 cursor-default items-center gap-3 rounded-md px-3">
      <span className="text-muted">{icon}</span>
      <span className="flex-1 truncate">{label}</span>
      {kbd && <Kbd>{kbd}</Kbd>}
    </Command.Item>
  )

  return (
    <div className="fixed inset-0 z-50 flex justify-center bg-black/40 pt-[12vh] animate-fade-in" onMouseDown={close}>
      <div onMouseDown={(e) => e.stopPropagation()} className="h-fit w-[620px] overflow-hidden rounded-xl border border-line bg-panel shadow-pop animate-slide-in">
        <Command label="Commands" loop onKeyDown={(e) => e.key === 'Escape' && close()}>
          <div className="flex items-center gap-2 border-b border-line px-4">
            <Search size={16} className="text-faint" />
            <Command.Input
              autoFocus
              value={q}
              onValueChange={setQ}
              placeholder="Type a command, an element or a session…"
              className="h-12 flex-1 bg-transparent text-[14px] outline-none placeholder:text-faint"
            />
          </div>
          <Command.List className="max-h-[420px] overflow-y-auto p-2">
            <Command.Empty className="p-6 text-center text-muted">No results.</Command.Empty>
            <Command.Group heading="Actions">
              {item(<Camera size={15} />, 'Capture & Analyze', captureAndAnalyze, 'F5')}
              {session && item(<RefreshCw size={15} />, 'Re-analyze this screenshot', reanalyze, 'F6')}
              {item(<FileUp size={15} />, 'Analyze an image…', openImage, 'Ctrl O')}
              {item(<FileJson size={15} />, 'Open a Visual DOM…', openDom, 'Ctrl D')}
              {session && item(<Upload size={15} />, 'Export Robot resource…', () => s.setExport(true), 'Ctrl E')}
              {item(<Settings2 size={15} />, 'Open a session config file…', () => {
                s.setView('settings')
                openConfig()
              })}
            </Command.Group>
            <Command.Group heading="View">
              {item(<ScanSearch size={15} />, 'Go to Inspect', () => s.setView('inspect'), 'Ctrl 1')}
              {item(<LayoutGrid size={15} />, 'Go to Sessions', () => s.setView('sessions'), 'Ctrl 2')}
              {item(<Server size={15} />, 'Go to Services', () => s.setView('services'), 'Ctrl 3')}
              {item(<Settings2 size={15} />, 'Go to Settings', () => s.setView('settings'), 'Ctrl ,')}
              {session && item(<Maximize size={15} />, 'Fit screenshot to view', () => s.fit(), 'Ctrl 0')}
              {session && item(<Tag size={15} />, 'Toggle element ids on the canvas', () => s.toggleLabels())}
              {item(<Moon size={15} />, 'Toggle dark / light theme', () => {
                s.setDark(!useStudio.getState().dark)
                window.studio.setPrefs({ theme: useStudio.getState().dark ? 'dark' : 'light' })
              })}
            </Command.Group>
            {session && q.length > 0 && (
              <Command.Group heading="Elements on this screen">
                {session.elements.slice(0, 400).map((e) =>
                  item(
                    <Crosshair size={15} />,
                    `${displayName(e)}  ·  ${e.id}`,
                    () => {
                      s.setView('inspect')
                      s.select(e.id)
                    },
                    undefined,
                    `element ${e.id} ${e.text ?? ''} ${e.role ?? ''}`
                  )
                )}
              </Command.Group>
            )}
            {recent.length > 0 && (
              <Command.Group heading="Recent sessions">
                {recent.map((r) =>
                  item(
                    <LayoutGrid size={15} />,
                    `${r.window_title || 'Screen'} — ${sessionDate(r.id)} (${r.element_count ?? '?'} elements)`,
                    () => s.openSession(r.id),
                    undefined,
                    `session ${r.id} ${r.window_title ?? ''}`
                  )
                )}
              </Command.Group>
            )}
          </Command.List>
        </Command>
      </div>
    </div>
  )
}
