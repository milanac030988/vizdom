import { FolderOpen, PlugZap, RotateCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { BridgeInfo } from '../../../shared/types'
import { Button, Input, Spinner } from './ui'

/** Shown until the Python bridge answers; explains and fixes a failed start. */
export function BridgeGate({ info }: { info: BridgeInfo }) {
  const [python, setPython] = useState(info.python)
  useEffect(() => setPython(info.python), [info.python])
  const starting = info.state === 'starting'

  return (
    <div className="drag flex h-full items-center justify-center p-10">
      <div className="no-drag w-full max-w-xl rounded-2xl border border-line bg-panel p-8 shadow-pop">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-accent/15 text-accent">
            {starting ? <Spinner className="h-5 w-5" /> : <PlugZap size={22} />}
          </div>
          <div>
            <div className="text-[16px] font-semibold">{starting ? 'Starting the VizDOM engine…' : 'The VizDOM engine did not start'}</div>
            <div className="text-muted">
              {starting ? 'Loading the Python bridge. The models load later, on the first analysis.' : info.error}
            </div>
          </div>
        </div>

        {!starting && (
          <div className="mt-6 space-y-3">
            <div className="font-medium">Python interpreter with VizDOM's dependencies</div>
            <div className="flex gap-2">
              <Input value={python} onChange={(e) => setPython(e.target.value)} className="flex-1" placeholder="e.g. D:\Python\python39\python.exe" />
              <Button
                icon={<FolderOpen size={14} />}
                onClick={async () => {
                  const p = await window.studio.pickPython()
                  if (p) setPython(p)
                }}
              >
                Browse
              </Button>
            </div>
            <Button variant="primary" icon={<RotateCw size={14} />} onClick={() => window.studio.restartBridge(python)}>
              Start again
            </Button>
            <p className="text-[12px] text-muted">
              Repository: <code className="font-mono">{info.repo}</code>. The bridge runs <code className="font-mono">python -m vizdom_bridge</code> with{' '}
              <code className="font-mono">PYTHONPATH=src;tools</code>; it needs fastapi and uvicorn besides the pipeline's packages.
            </p>
          </div>
        )}

        {info.log.length > 0 && (
          <pre className="selectable mt-6 max-h-56 overflow-auto rounded-lg bg-bg p-3 font-mono text-[11px] text-muted">{info.log.slice(-40).join('\n')}</pre>
        )}
      </div>
    </div>
  )
}
