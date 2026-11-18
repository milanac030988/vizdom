import clsx from 'clsx'
import { Copy, FolderOpen, Save } from 'lucide-react'
import { useEffect, useState } from 'react'
import { copyText } from '../actions'
import { api } from '../api'
import { hasCaption } from '../lib/elements'
import { useStudio } from '../store'
import { Button, Input, Modal, Select, Spinner } from './ui'

type Scope = 'marked' | 'captioned' | 'all'

export function ExportDialog() {
  const open = useStudio((s) => s.exportOpen)
  const session = useStudio((s) => s.session)
  const marked = useStudio((s) => s.marked)
  const setExport = useStudio((s) => s.setExport)
  const toast = useStudio((s) => s.toast)
  const [scope, setScope] = useState<Scope>('captioned')
  const [naming, setNaming] = useState('text_first')
  const [title, setTitle] = useState('UI Elements')
  const [preview, setPreview] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (open) {
      setScope(marked.size ? 'marked' : 'captioned')
      setTitle(session?.info.window_title ? `${session.info.window_title} elements` : 'UI Elements')
    }
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  const ids = (): string[] | null => {
    if (!session) return []
    if (scope === 'all') return null
    if (scope === 'marked') return [...marked]
    return session.elements.filter(hasCaption).map((e) => e.id)
  }
  const count = scope === 'all' ? (session?.elements.length ?? 0) : (ids()?.length ?? 0)

  useEffect(() => {
    if (!open || !session) return
    const list = ids()
    if (list && list.length === 0) {
      setPreview('')
      return
    }
    setLoading(true)
    api
      .exportPreview(session.id, list, naming)
      .then((r) => setPreview(r.content))
      .catch((e) => setPreview(`# ${e.message}`))
      .finally(() => setLoading(false))
  }, [open, scope, naming, session, marked]) // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    if (!session) return
    const safe = title.replace(/[^\w.-]+/g, '_').replace(/^_+|_+$/g, '') || 'ui_elements'
    const path = await window.studio.saveResource(`${safe}.resource`)
    if (!path) return
    try {
      const r = await api.exportFile(session.id, ids(), naming, title, path)
      setExport(false)
      toast({
        kind: 'ok',
        title: `Exported ${r.count} elements`,
        body: r.path,
        action: { label: 'Show in folder', run: () => window.studio.revealPath(r.path) }
      })
    } catch (e) {
      toast({ kind: 'error', title: 'Export failed', body: (e as Error).message })
    }
  }

  const scopeBtn = (s: Scope, label: string, n: number) => (
    <button
      onClick={() => setScope(s)}
      disabled={n === 0}
      className={clsx(
        'flex-1 rounded-md border px-3 py-2 text-left transition-colors disabled:opacity-40',
        scope === s ? 'border-accent bg-accent/10' : 'border-line hover:bg-raised'
      )}
    >
      <div className="font-medium">{label}</div>
      <div className="text-[12px] text-muted">{n} elements</div>
    </button>
  )

  return (
    <Modal
      open={open}
      onClose={() => setExport(false)}
      title="Export a Robot Framework resource"
      width={860}
      footer={
        <>
          <span className="mr-auto text-[12px] text-muted">
            Locators are written exactly as Studio resolves them: semantic part first, element id as the last fallback.
          </span>
          <Button icon={<Copy size={14} />} disabled={!preview} onClick={() => copyText(preview, 'Resource copied')}>
            Copy
          </Button>
          <Button variant="primary" icon={<Save size={14} />} disabled={count === 0} onClick={save}>
            Save {count} elements…
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-[320px_1fr]">
        <div className="space-y-1 border-r border-line p-4">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted">What to export</div>
          <div className="flex flex-col gap-2">
            {scopeBtn('marked', 'Marked elements', marked.size)}
            {scopeBtn('captioned', 'Elements with a caption', session?.elements.filter(hasCaption).length ?? 0)}
            {scopeBtn('all', 'Everything', session?.elements.length ?? 0)}
          </div>
          <div className="space-y-1.5 pt-3">
            <div className="font-medium">Variable names</div>
            <Select
              value={naming}
              onChange={setNaming}
              className="w-full"
              options={[
                { value: 'text_first', label: 'From the text: ${SAVE}' },
                { value: 'type_first', label: 'Type, then text: ${BUTTON_SAVE}' },
                { value: 'id_only', label: 'Element id: ${E7}' }
              ]}
            />
          </div>
          <div className="space-y-1.5 pt-2">
            <div className="font-medium">Title</div>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          {marked.size === 0 && (
            <p className="flex items-start gap-2 pt-3 text-[12px] text-muted">
              <FolderOpen size={14} className="mt-0.5 shrink-0" />
              Tip: hover a row in the element list and tick it to build a hand-picked export.
            </p>
          )}
        </div>
        <div className="relative min-h-[420px] bg-bg">
          {loading && <Spinner className="absolute right-3 top-3 text-muted" />}
          <pre className="selectable h-[460px] overflow-auto p-4 font-mono text-[12px] leading-relaxed text-ink">{preview || '# nothing to export'}</pre>
        </div>
      </div>
    </Modal>
  )
}
