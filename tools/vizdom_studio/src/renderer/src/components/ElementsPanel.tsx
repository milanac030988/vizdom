import clsx from 'clsx'
import { ChevronRight, List, ListTree, Search, SquareCheck, Square } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { categoryColor, categoryOf, displayName, hasCaption, matchesQuery } from '../lib/elements'
import { useStudio } from '../store'
import type { DomElement, Outline } from '../types'
import { IconButton, Input, Kbd, PanelHeader } from './ui'

export function ElementsPanel() {
  const session = useStudio((s) => s.session)
  const selectedId = useStudio((s) => s.selectedId)
  const hoverId = useStudio((s) => s.hoverId)
  const marked = useStudio((s) => s.marked)
  const focusTick = useStudio((s) => s.focusSearchTick)
  const { select, hover, toggleMark } = useStudio.getState()

  const [q, setQ] = useState('')
  const [mode, setMode] = useState<'flat' | 'tree'>('flat')
  const [captionedOnly, setCaptionedOnly] = useState(false)
  const search = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (focusTick) search.current?.focus()
  }, [focusTick])

  const byId = useMemo(() => new Map((session?.elements ?? []).map((e) => [e.id, e])), [session])
  const filtered = useMemo(
    () => (session?.elements ?? []).filter((e) => matchesQuery(e, q) && (!captionedOnly || hasCaption(e))),
    [session, q, captionedOnly]
  )

  // keep the selected row visible
  useEffect(() => {
    if (!selectedId) return
    document.getElementById(`row-${selectedId}`)?.scrollIntoView({ block: 'nearest' })
  }, [selectedId])

  if (!session) return null

  const row = (e: DomElement, depth = 0, toggle?: React.ReactNode) => {
    const c = categoryOf(e)
    const isSel = e.id === selectedId
    return (
      <div
        key={e.id}
        id={`row-${e.id}`}
        onClick={() => select(e.id)}
        onMouseEnter={() => hover(e.id)}
        onMouseLeave={() => hover(null)}
        className={clsx(
          'group flex h-8 cursor-default items-center gap-2 pr-2 text-[13px]',
          isSel ? 'bg-accent/15 text-ink' : e.id === hoverId ? 'bg-raised' : 'hover:bg-raised'
        )}
        style={{ paddingLeft: 8 + depth * 14 }}
      >
        {toggle ?? (mode === 'tree' ? <span className="w-3.5" /> : null)}
        <span className="h-2 w-2 shrink-0 rounded-sm" style={{ background: categoryColor(c) }} />
        <span className={clsx('min-w-0 flex-1 truncate', !hasCaption(e) && 'italic text-muted')}>{displayName(e)}</span>
        <span className="shrink-0 font-mono text-[11px] text-faint">{e.id}</span>
        <button
          title={marked.has(e.id) ? 'Remove from export' : 'Add to export'}
          onClick={(ev) => {
            ev.stopPropagation()
            toggleMark(e.id)
          }}
          className={clsx('shrink-0 text-faint hover:text-accent', marked.has(e.id) ? 'text-accent' : 'opacity-0 group-hover:opacity-100')}
        >
          {marked.has(e.id) ? <SquareCheck size={14} /> : <Square size={14} />}
        </button>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-panel">
      <PanelHeader title={`Elements · ${filtered.length}${filtered.length !== session.elements.length ? ` of ${session.elements.length}` : ''}`}>
        <IconButton label="Flat list in reading order" active={mode === 'flat'} onClick={() => setMode('flat')}>
          <List size={15} />
        </IconButton>
        <IconButton label="Hierarchy" active={mode === 'tree'} onClick={() => setMode('tree')}>
          <ListTree size={15} />
        </IconButton>
      </PanelHeader>
      <div className="space-y-2 border-b border-line p-2">
        <div className="relative">
          <Input
            ref={search}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') setQ('')
              if (e.key === 'Enter' && filtered[0]) select(filtered[0].id)
            }}
            placeholder="Filter by text, role, id…"
            icon={<Search size={14} />}
          />
          {!q && <Kbd className="pointer-events-none absolute right-2 top-[7px]">Ctrl F</Kbd>}
        </div>
        <label className="flex items-center gap-2 px-0.5 text-[12px] text-muted">
          <input type="checkbox" checked={captionedOnly} onChange={(e) => setCaptionedOnly(e.target.checked)} className="accent-[rgb(var(--accent))]" />
          Only elements with a caption (locatable by text)
        </label>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto py-1">
        {mode === 'flat' || q || captionedOnly || !session.hierarchy
          ? filtered.map((e) => row(e))
          : session.hierarchy.children.map((n) => <TreeNode key={n.id} node={n} depth={0} byId={byId} row={row} />)}
        {filtered.length === 0 && <div className="p-6 text-center text-muted">No element matches “{q}”.</div>}
      </div>
    </div>
  )
}

function TreeNode({
  node,
  depth,
  byId,
  row
}: {
  node: Outline
  depth: number
  byId: Map<string, DomElement>
  row: (e: DomElement, depth: number, toggle?: React.ReactNode) => React.ReactNode
}) {
  const [open, setOpen] = useState(depth < 2)
  const e = byId.get(node.id)
  const kids = node.children
  if (!e) return <>{kids.map((k) => <TreeNode key={k.id} node={k} depth={depth} byId={byId} row={row} />)}</>
  const toggle = kids.length ? (
    <button
      onClick={(ev) => {
        ev.stopPropagation()
        setOpen(!open)
      }}
      className="flex w-3.5 shrink-0 items-center justify-center text-faint hover:text-ink"
    >
      <ChevronRight size={13} className={clsx('transition-transform', open && 'rotate-90')} />
    </button>
  ) : (
    <span className="w-3.5 shrink-0" />
  )
  return (
    <>
      {row(e, depth, toggle)}
      {open && kids.map((k) => <TreeNode key={k.id} node={k} depth={depth + 1} byId={byId} row={row} />)}
    </>
  )
}
