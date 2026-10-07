import { AlertTriangle, RefreshCw, Loader2, Info } from 'lucide-react'
import { AiGlyph } from './brand'

// ---------------------------------------------------------------------------
// Card
// ---------------------------------------------------------------------------
export function Card({ children, className = '', ...props }) {
  return (
    <div className={`card ${className}`} {...props}>
      {children}
    </div>
  )
}

export function CardHeader({ title, subtitle, actions, icon: Icon, className = '' }) {
  return (
    <div
      className={`flex flex-wrap items-start justify-between gap-3 border-b border-ink-200/70 px-5 py-4 ${className}`}
    >
      <div className="flex items-start gap-3 min-w-0">
        {Icon && (
          <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-brand-400/20 bg-brand-50 text-brand-300">
            <Icon size={18} />
          </span>
        )}
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-ink-800 leading-tight">{title}</h2>
          {subtitle && <p className="mt-0.5 text-sm text-ink-500 leading-snug">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// The mandatory "AI-generated" notice, shown on every agent output
// ---------------------------------------------------------------------------
export function AiLabel({ className = '', compact = false }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border border-purple-400/25 bg-purple-50/50 text-purple-300 font-semibold ${
        compact ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-1 text-xs'
      } ${className}`}
    >
      <AiGlyph size={compact ? 11 : 13} />
      AI-generated — review before use
    </span>
  )
}

export function DraftBadge({ status }) {
  const map = {
    draft: { text: 'Draft', className: 'bg-amber-50 text-amber-800 border-amber-200' },
    approved: { text: 'Approved', className: 'bg-emerald-50 text-emerald-800 border-emerald-200' },
    needs_review: {
      text: 'Needs review',
      className: 'bg-rose-50 text-rose-800 border-rose-200',
    },
    sent: { text: 'Sent', className: 'bg-brand-50 text-brand-800 border-brand-200' },
    simulated_sent: {
      text: 'Simulated send',
      className: 'bg-sky-50 text-sky-800 border-sky-200',
    },
    failed: { text: 'Failed', className: 'bg-red-50 text-red-800 border-red-200' },
  }
  const entry = map[status] || {
    text: status || 'unknown',
    className: 'bg-ink-100 text-ink-700 border-ink-200',
  }
  return <span className={`chip ${entry.className}`}>{entry.text}</span>
}

// ---------------------------------------------------------------------------
// Confidence badge (grader)
// ---------------------------------------------------------------------------
export function ConfidenceBadge({ confidence }) {
  const value = Number(confidence ?? 1)
  const pct = Math.round(value * 100)
  let style = 'bg-emerald-50 text-emerald-800 border-emerald-200'
  let word = 'High'
  if (value < 0.6) {
    style = 'bg-red-50 text-red-800 border-red-200'
    word = 'Low'
  } else if (value < 0.8) {
    style = 'bg-amber-50 text-amber-800 border-amber-200'
    word = 'Medium'
  }
  return (
    <span
      title={`Grader confidence: ${pct}%${value < 0.6 ? ' — teacher review required' : ''}`}
      className={`chip ${style} tabular-nums`}
    >
      {word} {pct}%
    </span>
  )
}

// ---------------------------------------------------------------------------
// Loading
// ---------------------------------------------------------------------------
export function Skeleton({ className = '' }) {
  return <div className={`skeleton ${className}`} />
}

export function SkeletonCard({ lines = 3 }) {
  return (
    <Card className="card-pad">
      <Skeleton className="h-5 w-1/3 mb-4" />
      {Array.from({ length: lines }).map((_, index) => (
        <Skeleton key={index} className={`h-3.5 mb-2 ${index % 3 === 2 ? 'w-3/4' : 'w-full'}`} />
      ))}
    </Card>
  )
}

export function SkeletonTable({ rows = 5, cols = 4 }) {
  return (
    <div className="space-y-2 p-4">
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div key={rowIndex} className="flex gap-3">
          {Array.from({ length: cols }).map((_, colIndex) => (
            <Skeleton key={colIndex} className={`h-9 ${colIndex === 0 ? 'w-1/4' : 'flex-1'}`} />
          ))}
        </div>
      ))}
    </div>
  )
}

export function Spinner({ size = 16, className = '' }) {
  return <Loader2 size={size} className={`animate-spin ${className}`} />
}

export function LoadingPanel({ label = 'Working…', hint = '' }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-14 text-center">
      <div className="relative">
        <span className="absolute inset-0 rounded-full bg-brand-400/40 animate-ping" />
        <span className="relative grid h-12 w-12 place-items-center rounded-full bg-brand-500 text-ink-50">
          <Spinner size={22} />
        </span>
      </div>
      <p className="text-sm font-medium text-ink-700">{label}</p>
      {hint && <p className="max-w-sm text-xs text-ink-400">{hint}</p>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Errors & empty states
// ---------------------------------------------------------------------------
export function ErrorBanner({ error, onRetry, className = '' }) {
  if (!error) return null
  const message = typeof error === 'string' ? error : error.message || 'Something went wrong.'
  const problems = error.problems || []
  return (
    <div
      role="alert"
      className={`rounded-lg border border-red-200 bg-red-50 px-4 py-3 ${className}`}
    >
      <div className="flex items-start gap-3">
        <AlertTriangle size={18} className="shrink-0 mt-0.5 text-red-600" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-red-900">Something went wrong</p>
          <p className="mt-0.5 text-sm text-red-800 break-words">{message}</p>
          {problems.length > 0 && (
            <ul className="mt-2 space-y-0.5 text-xs text-red-700">
              {problems.slice(0, 5).map((problem, index) => (
                <li key={index}>• {problem}</li>
              ))}
            </ul>
          )}
        </div>
        {onRetry && (
          <button onClick={onRetry} className="btn-sm btn-secondary shrink-0">
            <RefreshCw size={13} />
            Retry
          </button>
        )}
      </div>
    </div>
  )
}

export function EmptyState({ icon: Icon = Info, title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
      <span className="grid h-12 w-12 place-items-center rounded-full bg-ink-200/70 text-ink-400">
        <Icon size={22} />
      </span>
      <p className="text-sm font-semibold text-ink-700">{title}</p>
      {description && <p className="max-w-sm text-sm text-ink-400">{description}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Misc
// ---------------------------------------------------------------------------
export function Stat({ label, value, hint, icon: Icon, tone = 'brand' }) {
  const tones = {
    brand: 'bg-brand-50 text-brand-700',
    accent: 'bg-accent-50 text-accent-600',
    violet: 'bg-purple-50 text-purple-700',
    sky: 'bg-sky-50 text-sky-700',
  }
  return (
    <Card className="card-pad">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-500">
            {label}
          </p>
          <p className="mt-1.5 text-2xl font-bold text-ink-800 tabular-nums">{value}</p>
          {hint && <p className="mt-1 text-xs text-ink-500">{hint}</p>}
        </div>
        {Icon && (
          <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-lg ${tones[tone]}`}>
            <Icon size={19} />
          </span>
        )}
      </div>
    </Card>
  )
}

export function Field({ label, hint, error, children, required }) {
  return (
    <div>
      <label className="label">
        {label}
        {required && <span className="ml-0.5 text-red-300">*</span>}
      </label>
      {children}
      {hint && !error && <p className="mt-1 text-xs text-ink-500">{hint}</p>}
      {error && <p className="mt-1 text-xs font-medium text-red-600">{error}</p>}
    </div>
  )
}

export function Toggle({ checked, onChange, label, description, disabled }) {
  return (
    <label
      className={`flex items-start gap-3 ${disabled ? 'opacity-60' : 'cursor-pointer'}`}
    >
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => !disabled && onChange(!checked)}
        className={`relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 ${
          checked ? 'bg-brand-500' : 'bg-ink-300'
        }`}
      >
        <span
          className={`absolute top-0.5 h-5 w-5 rounded-full shadow transition-transform ${
            // The track is polished steel when on, so the knob goes black rather
            // than white - a white knob on a silver track would vanish.
            checked ? 'translate-x-[22px] bg-ink-50' : 'translate-x-0.5 bg-white'
          }`}
        />
      </button>
      <span className="min-w-0">
        <span className="block text-sm font-medium text-ink-700">{label}</span>
        {description && <span className="block text-xs text-ink-500">{description}</span>}
      </span>
    </label>
  )
}

export function Tabs({ tabs, active, onChange, className = '' }) {
  return (
    <div className={`flex gap-1 overflow-x-auto border-b border-ink-200 ${className}`}>
      {tabs.map((tab) => (
        <button
          key={tab.key}
          onClick={() => onChange(tab.key)}
          className={`relative whitespace-nowrap px-4 py-2.5 text-sm font-medium transition-colors ${
            active === tab.key
              ? 'text-brand-700 after:absolute after:inset-x-0 after:-bottom-px after:h-0.5 after:bg-brand-600'
              : 'text-ink-500 hover:text-ink-700'
          }`}
        >
          {tab.label}
          {tab.count !== undefined && tab.count !== null && (
            <span className="ml-1.5 rounded-full bg-ink-100 px-1.5 py-0.5 text-[10px] font-semibold text-ink-600">
              {tab.count}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}

/** Render text, giving Devanagari a bit more breathing room. */
export function T({ children, className = '' }) {
  const text = typeof children === 'string' ? children : ''
  const devanagari = /[\u0900-\u097F]/.test(text)
  return <span className={`${devanagari ? 'devanagari' : ''} ${className}`}>{children}</span>
}