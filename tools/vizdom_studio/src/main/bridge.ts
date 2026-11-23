/**
 * Starts and supervises the Python bridge (tools/vizdom_bridge).
 *
 * The bridge binds 127.0.0.1 on a free port and requires a per-launch token,
 * so nothing else on the machine can drive the pipeline or the actuator.
 */
import { ChildProcess, spawn } from 'child_process'
import { randomBytes } from 'crypto'
import { app } from 'electron'
import { existsSync, mkdirSync } from 'fs'
import { delimiter, join, resolve } from 'path'
import type { BridgeInfo } from '../shared/types'

/**
 * The installed Studio carries everything in its resources folder, laid out by
 * scripts/bundle_python.ps1:
 *   python/      a relocatable CPython with VizDOM, the Robot Framework library,
 *                the bridge's web server and CPU torch installed
 *   vizdom/      tools/vizdom_bridge, tools/visual_dom_viewer, plugins/, the example config
 *   easyocr/     the EasyOCR English models, so the first analysis works offline
 *   tesseract/   the Tesseract engine (EasyOCR's fallback for hard-to-read text)
 * A source checkout has none of these and runs against the repository instead.
 */
const resourceDir = (name: string): string | null => {
  if (!app.isPackaged) return null
  const dir = join(process.resourcesPath, name)
  return existsSync(dir) ? dir : null
}

export function bundledPython(): string | null {
  const dir = resourceDir('python')
  if (!dir) return null
  const exe = process.platform === 'win32' ? join(dir, 'python.exe') : join(dir, 'bin', 'python3')
  return existsSync(exe) ? exe : null
}

/** Where the user's session config, sessions and plugins live (writable). */
export function dataHome(): string {
  if (process.env.VIZDOM_HOME) return resolve(process.env.VIZDOM_HOME)
  if (app.isPackaged) return join(app.getPath('documents'), 'VizDOM')
  return repoRoot()
}

export function repoRoot(): string {
  if (process.env.VIZDOM_REPO) return resolve(process.env.VIZDOM_REPO)
  const bundled = resourceDir('vizdom')
  if (bundled) return bundled
  // out/main -> tools/vizdom_studio/out/main: four levels below the repository
  let dir = resolve(__dirname)
  for (let i = 0; i < 6; i++) {
    if (existsSync(join(dir, 'src', 'visual_dom')) && existsSync(join(dir, 'tools'))) return dir
    dir = resolve(dir, '..')
  }
  return resolve(__dirname, '..', '..', '..', '..')
}

export class Bridge {
  private proc: ChildProcess | null = null
  private configPath = ''
  private listeners = new Set<(info: BridgeInfo) => void>()
  info: BridgeInfo

  constructor(private python: string) {
    this.info = { state: 'starting', url: null, token: null, python, repo: repoRoot(), error: null, log: [] }
  }

  onChange(cb: (info: BridgeInfo) => void): () => void {
    this.listeners.add(cb)
    return () => this.listeners.delete(cb)
  }

  private set(patch: Partial<BridgeInfo>): void {
    this.info = { ...this.info, ...patch }
    for (const cb of this.listeners) cb(this.info)
  }

  private log(line: string): void {
    const log = [...this.info.log, line].slice(-300)
    this.set({ log })
  }

  /** The services this bridge started that are still running, e.g. "Detector (port 50051)". */
  async ownedServices(): Promise<string[]> {
    const { url, token } = this.info
    if (!this.proc || !url || !token) return []
    try {
      const r = await fetch(`${url}/api/services`, {
        headers: { 'X-VizDOM-Token': token },
        signal: AbortSignal.timeout(4000)
      })
      const list = (await r.json()) as { title: string; port: number; owned: boolean }[]
      return list.filter((s) => s.owned).map((s) => `${s.title} (port ${s.port})`)
    } catch {
      return []
    }
  }

  /** Ask the bridge to stop the services it started, then end it. */
  async shutdown(): Promise<void> {
    const { url, token } = this.info
    if (this.proc && url && token) {
      try {
        await fetch(`${url}/api/shutdown`, {
          method: 'POST',
          headers: { 'X-VizDOM-Token': token },
          signal: AbortSignal.timeout(20000)
        })
      } catch {
        /* the bridge may already be gone */
      }
    }
    this.stop()
  }

  async start(python?: string, configPath?: string): Promise<BridgeInfo> {
    await this.shutdown()
    if (python) this.python = python
    if (configPath !== undefined) this.configPath = configPath
    const repo = repoRoot()
    const token = randomBytes(24).toString('hex')
    this.set({ state: 'starting', url: null, token: null, python: this.python, repo, error: null, log: [] })

    const home = dataHome()
    const env: NodeJS.ProcessEnv = {
      ...process.env,
      PYTHONPATH: [join(repo, 'src'), join(repo, 'tools'), process.env.PYTHONPATH || '']
        .filter(Boolean)
        .join(delimiter),
      PYTHONIOENCODING: 'utf-8',
      PYTHONUNBUFFERED: '1',
      USE_TF: '0',
      VIZDOM_REPO: repo,
      VIZDOM_HOME: home
    }
    if (app.isPackaged) {
      // the user's own plugins sit beside their sessions, not inside the install
      for (const kind of ['capture', 'actuator']) {
        const dir = join(home, 'plugins', kind)
        try {
          mkdirSync(dir, { recursive: true })
        } catch {
          /* a read-only Documents folder only loses plugin discovery */
        }
        const key = `VIZDOM_${kind.toUpperCase()}_PLUGINS`
        if (!env[key]) env[key] = dir
      }
      const easyocr = resourceDir('easyocr')
      if (easyocr && !env.EASYOCR_MODULE_PATH) env.EASYOCR_MODULE_PATH = easyocr
      const tesseract = resourceDir('tesseract')
      if (tesseract) {
        const pathKey = Object.keys(env).find((k) => k.toUpperCase() === 'PATH') || 'PATH'
        env[pathKey] = [tesseract, env[pathKey] || ''].filter(Boolean).join(delimiter)
      }
    }
    let proc: ChildProcess
    try {
      const args = ['-m', 'vizdom_bridge', '--port', '0', '--token', token]
      // a remembered config that was moved or deleted falls back to the default
      if (this.configPath && existsSync(this.configPath)) args.push('--config', this.configPath)
      mkdirSync(home, { recursive: true })
      proc = spawn(this.python, args, {
        cwd: home,
        env,
        windowsHide: true
      })
    } catch (e) {
      this.set({ state: 'failed', error: `Could not start ${this.python}: ${String(e)}` })
      return this.info
    }
    this.proc = proc

    return new Promise<BridgeInfo>((done) => {
      let settled = false
      const finish = (patch: Partial<BridgeInfo>): void => {
        if (settled) return
        settled = true
        this.set(patch)
        done(this.info)
      }
      const timer = setTimeout(
        () => finish({ state: 'failed', error: 'The bridge did not report ready within 60 s.' }),
        60_000
      )
      const onLine = (line: string): void => {
        if (!line.trim()) return
        this.log(line)
        const m = /VIZDOM_BRIDGE_READY port=(\d+)/.exec(line)
        if (m) {
          const url = `http://127.0.0.1:${m[1]}`
          waitHealthy(url, token).then((ok) => {
            clearTimeout(timer)
            finish(ok ? { state: 'ready', url, token } : { state: 'failed', error: 'The bridge started but does not answer.' })
          })
        }
      }
      const pipe = (stream: NodeJS.ReadableStream | null): void => {
        let buf = ''
        stream?.on('data', (chunk: Buffer) => {
          buf += chunk.toString('utf8')
          const lines = buf.split(/\r?\n/)
          buf = lines.pop() ?? ''
          lines.forEach(onLine)
        })
      }
      pipe(proc.stdout)
      pipe(proc.stderr)
      proc.on('error', (err) => {
        clearTimeout(timer)
        finish({
          state: 'failed',
          error: `Could not start "${this.python}" (${err.message}). Set the Python interpreter that has VizDOM's dependencies.`
        })
      })
      proc.on('exit', (code) => {
        clearTimeout(timer)
        if (this.proc === proc) this.proc = null
        if (!settled) {
          finish({ state: 'failed', error: `The bridge exited with code ${code} before it was ready.` })
        } else if (this.info.state === 'ready') {
          this.set({ state: 'failed', error: `The bridge stopped (exit code ${code}).` })
        }
      })
    })
  }

  stop(): void {
    const p = this.proc
    this.proc = null
    if (p && p.exitCode === null) {
      try {
        p.kill()
      } catch {
        /* already gone */
      }
    }
  }
}

async function waitHealthy(url: string, token: string): Promise<boolean> {
  for (let i = 0; i < 80; i++) {
    try {
      const r = await fetch(`${url}/api/health`, { headers: { 'X-VizDOM-Token': token } })
      if (r.ok) return true
    } catch {
      /* not listening yet */
    }
    await new Promise((r) => setTimeout(r, 250))
  }
  return false
}
