// split     = { alsabini: '€123', other: '€456' }         — legacy two-key breakdown
// breakdown = [{ label, value, sub?, colour? }, ...]       — generic multi-item breakdown
// onClick   = function — makes card clickable (shows trend arrow hint)
export default function KPICard({ label, value, sub, colour = 'blue', icon, split, breakdown, onClick }) {
  const colours = {
    blue:   'bg-gradient-to-br from-blue-50   to-blue-100/70   border-blue-200/80   text-blue-700',
    green:  'bg-gradient-to-br from-emerald-50 to-emerald-100/70 border-emerald-200/80 text-emerald-700',
    amber:  'bg-gradient-to-br from-amber-50  to-amber-100/70  border-amber-200/80  text-amber-700',
    red:    'bg-gradient-to-br from-red-50    to-red-100/70    border-red-200/80    text-red-700',
    slate:  'bg-gradient-to-br from-slate-50  to-slate-100/70  border-slate-200/80  text-slate-600',
    violet: 'bg-gradient-to-br from-violet-50 to-violet-100/70 border-violet-200/80 text-violet-700',
    indigo: 'bg-gradient-to-br from-indigo-50 to-indigo-100/70 border-indigo-200/80 text-indigo-700',
    teal:   'bg-gradient-to-br from-teal-50   to-teal-100/70   border-teal-200/80   text-teal-700',
    sky:    'bg-gradient-to-br from-sky-50    to-sky-100/70    border-sky-200/80    text-sky-700',
    rose:   'bg-gradient-to-br from-rose-50   to-rose-100/70   border-rose-200/80   text-rose-700',
  }
  // Per-item accent colours for breakdown rows
  const itemAccent = {
    blue:   'bg-blue-100   text-blue-700',
    green:  'bg-emerald-100 text-emerald-700',
    amber:  'bg-amber-100  text-amber-700',
    violet: 'bg-violet-100 text-violet-700',
    indigo: 'bg-indigo-100 text-indigo-700',
    teal:   'bg-teal-100   text-teal-700',
    sky:    'bg-sky-100    text-sky-700',
    rose:   'bg-rose-100   text-rose-700',
    slate:  'bg-slate-100  text-slate-600',
  }

  const hasSplit     = split && (split.alsabini != null || split.other != null)
  const hasBreakdown = breakdown && breakdown.some(b => b.value != null)

  return (
    <div
      className={`card p-3 sm:p-5 flex flex-col gap-1 border ${colours[colour]}${onClick ? ' cursor-pointer hover:shadow-md active:scale-[0.98] transition-transform' : ''}`}
      onClick={onClick}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide opacity-70 leading-tight">{label}</span>
        <div className="flex items-center gap-1 shrink-0 ml-1">
          {onClick && <span className="text-[9px] opacity-40 font-normal normal-case tracking-normal">↗ trend</span>}
          {icon && <span className="text-base sm:text-lg">{icon}</span>}
        </div>
      </div>
      <div className="text-2xl sm:text-3xl font-extrabold text-slate-900 mt-1 leading-none tracking-tight">{value ?? '—'}</div>
      {sub && <div className="text-[10px] sm:text-xs text-slate-500 mt-0.5 leading-tight">{sub}</div>}

      {hasSplit && (
        <div className="border-t border-current/10 mt-1.5 pt-1.5 flex flex-wrap gap-x-2 gap-y-0.5 text-[10px]">
          {split.alsabini != null && (
            <span><span className="opacity-60">Alsabini</span>{' '}<span className="font-semibold">{split.alsabini}</span></span>
          )}
          {split.alsabini != null && split.other != null && <span className="opacity-30">·</span>}
          {split.other != null && (
            <span><span className="opacity-60">Other</span>{' '}<span className="font-semibold">{split.other}</span></span>
          )}
        </div>
      )}

      {hasBreakdown && (
        <div className="border-t border-current/10 mt-2 pt-2 flex flex-col gap-1.5">
          {breakdown.filter(b => b.value != null).map(b => {
            const accent = b.colour ? (itemAccent[b.colour] || itemAccent.slate) : null
            return (
              <div key={b.label} className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  {accent
                    ? <span className={`inline-block text-[10px] font-semibold px-1.5 py-0.5 rounded ${accent}`}>{b.label}</span>
                    : <span className="text-[10px] opacity-60">{b.label}</span>}
                  {b.sub && <div className="text-[9px] text-slate-400 leading-tight mt-0.5">{b.sub}</div>}
                </div>
                <span className="text-sm font-bold text-slate-800 shrink-0">{b.value}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
