/** User actions shared by the toolbar, the keyboard shortcuts and the command palette. */
import { api } from './api'
import { useStudio } from './store'
import type { Job } from './types'

const st = () => useStudio.getState()

function busy(): boolean {
  const j = st().job
  if (j && j.state === 'running') {
    st().toast({ kind: 'info', title: 'Still working', body: `${j.title} is running. One job at a time.` })
    return true
  }
  return false
}

function started(job: Job): void {
  st().setJob(job)
}

function failed(title: string, e: unknown): void {
  st().toast({ kind: 'error', title, body: (e as Error).message })
}

export async function captureAndAnalyze(): Promise<void> {
  if (busy()) return
  const title = st().targetWindow || null
  await window.studio.hideForCapture()
  try {
    started(await api.capture(title))
  } catch (e) {
    failed('Capture failed', e)
  } finally {
    await window.studio.showAfterCapture()
  }
}

export async function reanalyze(): Promise<void> {
  const s = st().session
  if (!s) return st().toast({ kind: 'info', title: 'Nothing to re-analyze', body: 'Capture or open a screen first.' })
  if (busy()) return
  try {
    started(await api.reanalyze(s.id))
  } catch (e) {
    failed('Re-analyze failed', e)
  }
}

export async function openImage(): Promise<void> {
  if (busy()) return
  const path = await window.studio.openImage()
  if (!path) return
  try {
    started(await api.analyzeFile(path))
  } catch (e) {
    failed('Could not analyze the image', e)
  }
}

export async function openDom(): Promise<void> {
  const path = await window.studio.openDom()
  if (!path) return
  try {
    const { session_id } = await api.importDom(path)
    await st().openSession(session_id)
  } catch (e) {
    failed('Could not open the DOM', e)
  }
}

export async function tryClick(locator: string, clickType: 'single' | 'double' | 'right' = 'single'): Promise<void> {
  const s = st().session
  if (!s || busy()) return
  try {
    started(
      await api.tryLocator(s.id, {
        locator,
        click_type: clickType,
        window_title: st().targetWindow || s.info.window_title || null,
        recapture_before: true,
        recapture_after: true
      })
    )
  } catch (e) {
    failed('Could not try the locator', e)
  }
}

/** Use another session config file; it is remembered for the next launch. */
export async function openConfig(): Promise<boolean> {
  const path = await window.studio.openConfig()
  if (!path) return false
  try {
    const cfg = await api.loadConfig(path)
    st().setConfig(cfg)
    await window.studio.setPrefs({ configPath: cfg.path })
    st().toast({ kind: 'ok', title: 'Config loaded', body: `${cfg.path} · ${cfg.summary.detector} · ${cfg.summary.ocr}` })
    return true
  } catch (e) {
    failed('Could not load the config', e)
    return false
  }
}

export async function saveConfigAs(): Promise<boolean> {
  const current = st().config?.path ?? ''
  const path = await window.studio.saveConfigAs(current)
  if (!path) return false
  try {
    const cfg = await api.saveConfig(path)
    st().setConfig(cfg)
    await window.studio.setPrefs({ configPath: cfg.path })
    st().toast({ kind: 'ok', title: 'Config saved', body: cfg.path })
    return true
  } catch (e) {
    failed('Could not save the config', e)
    return false
  }
}

export async function copyText(text: string, what = 'Copied'): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
    st().toast({ kind: 'ok', title: what, body: text.length > 90 ? text.slice(0, 90) + '…' : text })
  } catch {
    st().toast({ kind: 'error', title: 'Clipboard not available' })
  }
}

/** A finished job decides what the user sees next. */
export async function onJobFinished(job: Job): Promise<void> {
  const r = (job.result || {}) as Record<string, unknown>
  if (job.state === 'error') {
    st().toast({ kind: 'error', title: `${job.title} failed`, body: job.error || undefined })
    return
  }
  if (job.kind === 'analyze' && r.session_id) {
    await st().openSession(String(r.session_id))
    st().toast({
      kind: 'ok',
      title: `${r.element_count} elements found`,
      body: `${job.title} · ${job.elapsed ?? '?'} s`
    })
  } else if (job.kind === 'try') {
    const target = String(r.after_session_id || r.session_id || '')
    if (r.clicked) {
      if (target) await st().openSession(target, r.after_session_id ? null : String(r.element_id))
      st().toast({
        kind: 'ok',
        title: `Clicked ${r.element_id} via ${r.actuator}`,
        body: r.after_session_id ? 'The screen was captured again after the click.' : String(r.locator)
      })
    } else {
      if (r.session_id) await st().openSession(String(r.session_id))
      st().toast({
        kind: 'error',
        title: 'The locator did not resolve',
        body: `${r.error}. The same locator would fail in the suite.`
      })
    }
  }
}
