import { useEffect, useState } from 'react'
import type { BridgeInfo } from '../../shared/types'
import { captureAndAnalyze, onJobFinished, openDom, openImage, reanalyze } from './actions'
import { api, configureApi, connectEvents } from './api'
import { BridgeGate } from './components/BridgeGate'
import { JobProgress, NavRail, StatusBar, Toasts } from './components/Chrome'
import { CommandPalette } from './components/CommandPalette'
import { ExportDialog } from './components/ExportDialog'
import { TitleBar } from './components/TitleBar'
import { useStudio } from './store'
import { InspectView } from './views/InspectView'
import { serviceLogBus, ServicesView } from './views/ServicesView'
import { SessionsView } from './views/SessionsView'
import { SettingsView } from './views/SettingsView'

export function App() {
  const [bridge, setBridge] = useState<BridgeInfo | null>(null)
  const [connected, setConnected] = useState(false)
  const view = useStudio((s) => s.view)

  useEffect(() => {
    window.studio.prefs().then((p) => {
      const dark = p.theme === 'dark' || (p.theme === 'system' && matchMedia('(prefers-color-scheme: dark)').matches)
      useStudio.getState().setDark(dark)
    })
    window.studio.bridge().then(setBridge)
    return window.studio.onBridge(setBridge)
  }, [])

  const ready = bridge?.state === 'ready' && bridge.url && bridge.token
  // During render, not in an effect: children's effects run before this
  // component's, and the views fetch on mount.
  if (ready) configureApi(bridge!.url!, bridge!.token!)

  useEffect(() => {
    if (!ready) return
    const s = useStudio.getState()
    s.refreshConfig()
    s.refreshWindows()
    api.currentJob().then((j) => j && s.setJob(j), () => undefined)
    return connectEvents((e) => {
      if (e.type === 'job') {
        const prev = useStudio.getState().job
        useStudio.getState().setJob(e.job)
        if (e.job.state !== 'running' && !(prev && prev.id === e.job.id && prev.state !== 'running')) onJobFinished(e.job)
      } else if (e.type === 'service-log') {
        serviceLogBus.dispatchEvent(new CustomEvent('line', { detail: e }))
      } else if (e.type === 'services-changed') {
        serviceLogBus.dispatchEvent(new Event('changed'))
      }
    }, setConnected)
  }, [ready, bridge?.url, bridge?.token]) // eslint-disable-line react-hooks/exhaustive-deps

  // Global shortcuts
  useEffect(() => {
    if (!ready) return
    const onKey = (e: KeyboardEvent) => {
      const s = useStudio.getState()
      const mod = e.ctrlKey || e.metaKey
      const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes((e.target as HTMLElement)?.tagName)
      if (e.key === 'F5') return e.preventDefault(), captureAndAnalyze()
      if (e.key === 'F6') return e.preventDefault(), reanalyze()
      if (mod && e.key.toLowerCase() === 'k') return e.preventDefault(), s.setPalette(!s.paletteOpen)
      if (mod && e.key.toLowerCase() === 'o') return e.preventDefault(), openImage()
      if (mod && e.key.toLowerCase() === 'd') return e.preventDefault(), openDom()
      if (mod && e.key.toLowerCase() === 'e' && s.session) return e.preventDefault(), s.setExport(true)
      if (mod && e.key.toLowerCase() === 'f') return e.preventDefault(), s.focusSearch()
      if (mod && e.key === ',') return e.preventDefault(), s.setView('settings')
      if (mod && ['1', '2', '3'].includes(e.key)) {
        e.preventDefault()
        return s.setView((['inspect', 'sessions', 'services'] as const)[Number(e.key) - 1])
      }
      if (e.key === 'Escape' && !typing && s.selectedId) s.select(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [ready])

  if (!bridge) return null
  if (!ready)
    return (
      <div className="flex h-full flex-col">
        <div className="drag h-11 shrink-0 border-b border-line bg-panel" />
        <BridgeGate info={bridge} />
      </div>
    )

  return (
    <div className="flex h-full flex-col">
      <TitleBar />
      <div className="relative flex min-h-0 flex-1">
        <NavRail />
        <main className="relative min-w-0 flex-1">
          <JobProgress />
          {view === 'inspect' && <InspectView />}
          {view === 'sessions' && <SessionsView />}
          {view === 'services' && <ServicesView />}
          {view === 'settings' && <SettingsView />}
        </main>
      </div>
      <StatusBar connected={connected} />
      <CommandPalette />
      <ExportDialog />
      <Toasts />
    </div>
  )
}
