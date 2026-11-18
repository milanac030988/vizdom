import clsx from 'clsx'
import { X } from 'lucide-react'
import { forwardRef, useEffect, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'

export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: 'sm' | 'md'; icon?: ReactNode; kbd?: string }
>(function Button({ variant = 'secondary', size = 'md', icon, kbd, className, children, ...rest }, ref) {
  return (
    <button
      ref={ref}
      {...rest}
      className={clsx(
        'no-drag inline-flex select-none items-center gap-1.5 whitespace-nowrap rounded-md font-medium transition-colors',
        'disabled:cursor-not-allowed disabled:opacity-45',
        size === 'sm' ? 'h-7 px-2 text-[12px]' : 'h-8 px-3 text-[13px]',
        variant === 'primary' && 'bg-accent text-accent-ink shadow-sm hover:bg-accent/90',
        variant === 'secondary' && 'border border-line bg-raised text-ink hover:border-faint/60 hover:bg-raised/70',
        variant === 'ghost' && 'text-muted hover:bg-raised hover:text-ink',
        variant === 'danger' && 'border border-bad/40 bg-bad/10 text-bad hover:bg-bad/20',
        className
      )}
    >
      {icon}
      {children}
      {kbd && <Kbd className="ml-1 opacity-70">{kbd}</Kbd>}
    </button>
  )
})

export function IconButton({
  label,
  active,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; active?: boolean }) {
  return (
    <button
      {...rest}
      title={label}
      aria-label={label}
      className={clsx(
        'no-drag inline-flex h-8 w-8 items-center justify-center rounded-md transition-colors disabled:opacity-40',
        active ? 'bg-accent/15 text-accent' : 'text-muted hover:bg-raised hover:text-ink',
        className
      )}
    >
      {children}
    </button>
  )
}

export function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <kbd
      className={clsx(
        'inline-flex h-[18px] min-w-[18px] items-center justify-center rounded border border-line bg-bg px-1 font-mono text-[10px] text-muted',
        className
      )}
    >
      {children}
    </kbd>
  )
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & { icon?: ReactNode }>(
  function Input({ icon, className, ...rest }, ref) {
    return (
      <div className={clsx('relative flex items-center', className)}>
        {icon && <span className="pointer-events-none absolute left-2.5 text-faint">{icon}</span>}
        <input
          ref={ref}
          {...rest}
          className={clsx(
            'no-drag h-8 w-full rounded-md border border-line bg-bg text-[13px] text-ink placeholder:text-faint',
            'outline-none transition-colors focus:border-accent focus:ring-2 focus:ring-accent/20',
            icon ? 'pl-8 pr-2.5' : 'px-2.5'
          )}
        />
      </div>
    )
  }
)

export function Select({
  value,
  onChange,
  options,
  className
}: {
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string; disabled?: boolean }[]
  className?: string
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={clsx(
        'no-drag h-8 rounded-md border border-line bg-bg px-2 text-[13px] text-ink outline-none focus:border-accent',
        className
      )}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value} disabled={o.disabled}>
          {o.label}
        </option>
      ))}
    </select>
  )
}

export function Switch({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label?: string }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={clsx(
        'relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors',
        checked ? 'bg-accent' : 'bg-line'
      )}
    >
      <span
        className={clsx(
          'inline-block h-4 w-4 rounded-full bg-white shadow transition-transform',
          checked ? 'translate-x-[18px]' : 'translate-x-0.5'
        )}
      />
    </button>
  )
}

export function Badge({ children, tone = 'neutral', className }: { children: ReactNode; tone?: 'neutral' | 'accent' | 'ok' | 'warn' | 'bad'; className?: string }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded px-1.5 py-[1px] text-[11px] font-medium',
        tone === 'neutral' && 'bg-raised text-muted',
        tone === 'accent' && 'bg-accent/15 text-accent',
        tone === 'ok' && 'bg-ok/15 text-ok',
        tone === 'warn' && 'bg-warn/15 text-warn',
        tone === 'bad' && 'bg-bad/15 text-bad',
        className
      )}
    >
      {children}
    </span>
  )
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={clsx('inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-r-transparent', className)}
    />
  )
}

export function PanelHeader({ title, children }: { title: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex h-10 shrink-0 items-center gap-2 border-b border-line px-3">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">{title}</div>
      <div className="ml-auto flex items-center gap-1">{children}</div>
    </div>
  )
}

export function EmptyState({ icon, title, body, children }: { icon: ReactNode; title: string; body?: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-raised text-muted">{icon}</div>
      <div className="text-[15px] font-semibold">{title}</div>
      {body && <div className="max-w-sm text-muted">{body}</div>}
      {children && <div className="mt-2 flex flex-wrap items-center justify-center gap-2">{children}</div>}
    </div>
  )
}

export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  width = 640
}: {
  open: boolean
  onClose: () => void
  title: ReactNode
  children: ReactNode
  footer?: ReactNode
  width?: number
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-6 animate-fade-in" onMouseDown={onClose}>
      <div
        className="flex max-h-full flex-col overflow-hidden rounded-xl border border-line bg-panel shadow-pop animate-slide-in"
        style={{ width }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex h-12 items-center border-b border-line px-4">
          <div className="text-[14px] font-semibold">{title}</div>
          <IconButton label="Close" className="ml-auto" onClick={onClose}>
            <X size={16} />
          </IconButton>
        </div>
        <div className="min-h-0 flex-1 overflow-auto">{children}</div>
        {footer && <div className="flex items-center justify-end gap-2 border-t border-line px-4 py-3">{footer}</div>}
      </div>
    </div>
  )
}

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[200px_1fr] items-start gap-4 py-3">
      <div>
        <div className="font-medium">{label}</div>
        {hint && <div className="mt-0.5 text-[12px] leading-snug text-muted">{hint}</div>}
      </div>
      <div className="flex min-h-8 items-center gap-2">{children}</div>
    </div>
  )
}
