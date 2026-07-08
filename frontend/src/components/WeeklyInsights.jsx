import { useState, useEffect } from 'react'
import { TrendingDown, TrendingUp, Sparkles, ChevronDown } from 'lucide-react'
import { api } from '../api/client'

const fmtEur = v => `€${Number(v).toLocaleString('en-EU', { maximumFractionDigits: 0 })}`
const fmtNum = v => Number(v).toLocaleString()

const fmtWeek = iso => {
  if (!iso) return ''
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

const fmtMetric = (v, metric) => (metric === 'gmv' ? fmtEur(v) : fmtNum(v))
const metricWord = metric => (metric === 'gmv' ? 'GMV' : 'bookings')

// Tiny inline formatter for the brief: handles **bold** and *italic*.
function renderInline(text, keyPrefix) {
  const nodes = []
  let rest = text
  let i = 0
  const re = /\*\*(.+?)\*\*|\*(.+?)\*/g
  let lastIndex = 0
  let m
  while ((m = re.exec(text)) !== null) {
    if (m.index > lastIndex) nodes.push(text.slice(lastIndex, m.index))
    if (m[1] !== undefined) {
      nodes.push(<strong key={`${keyPrefix}-b${i++}`} className="font-semibold text-slate-800">{m[1]}</strong>)
    } else if (m[2] !== undefined) {
      nodes.push(<em key={`${keyPrefix}-i${i++}`} className="text-slate-400 not-italic">{m[2]}</em>)
    }
    lastIndex = re.lastIndex
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex))
  return nodes
}

// Colour-coded hotel / vendor tag — violet for hotels, blue for vendors.
const TAG_STYLE = {
  hotel:  'bg-violet-100 text-violet-700',
  vendor: 'bg-blue-100 text-blue-700',
}
function Tag({ kind }) {
  return (
    <span className={`mr-1.5 inline-block align-middle text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded ${TAG_STYLE[kind] || 'bg-slate-100 text-slate-500'}`}>
      {kind}
    </span>
  )
}

function Brief({ narrative }) {
  if (!narrative) return null
  const lines = narrative.split('\n')
  return (
    <div className="text-xs leading-relaxed text-slate-600 space-y-1.5">
      {lines.map((line, idx) => {
        if (!line.trim()) return <div key={idx} className="h-1" />
        if (line.trim().startsWith('- ')) {
          let content = line.trim().slice(2)
          // Pull a leading {{hotel}} / {{vendor}} tag, render it as a coloured chip
          let tag = null
          const tm = content.match(/^\{\{(hotel|vendor)\}\}/)
          if (tm) { tag = tm[1]; content = content.slice(tm[0].length) }
          return (
            <div key={idx} className="flex gap-1.5 pl-1">
              <span className="text-slate-300 shrink-0">•</span>
              <span>
                {tag && <Tag kind={tag} />}
                {renderInline(content, `l${idx}`)}
              </span>
            </div>
          )
        }
        return <p key={idx}>{renderInline(line, `l${idx}`)}</p>
      })}
    </div>
  )
}

function MoverRow({ rec, metric, kind, direction }) {
  const isDecline = direction === 'decline'
  const wow = rec.wow_pct
  const vsAvg = rec.vs_avg_pct
  const pillColour = isDecline
    ? 'bg-red-50 text-red-600'
    : 'bg-emerald-50 text-emerald-700'

  return (
    <div className="flex items-start justify-between gap-3 py-2 border-t border-slate-50 first:border-t-0">
      <div className="min-w-0">
        <p className="text-xs font-medium text-slate-700 truncate">
          <Tag kind={kind} />
          {rec.name}
        </p>
        <p className="text-[11px] text-slate-400 mt-0.5">
          {fmtMetric(rec.prior, metric)} → <span className="text-slate-600 font-medium">{fmtMetric(rec.this, metric)}</span>
          {' '}{metricWord(metric)}
          {vsAvg != null && (
            <span className="text-slate-400">
              {' · '}{vsAvg >= 0 ? '+' : ''}{vsAvg.toFixed(0)}% vs {rec.avg ? fmtMetric(rec.avg, metric) : ''} avg
            </span>
          )}
        </p>
      </div>
      <span className={`shrink-0 text-[11px] font-semibold px-2 py-0.5 rounded-full ${pillColour}`}>
        {rec.is_new ? 'NEW' : wow == null ? '—' : `${wow >= 0 ? '+' : ''}${wow.toFixed(0)}%`}
      </span>
    </div>
  )
}

// Module-level (stable identity) so the clickable bar is never remounted on a
// re-render — a remount mid-click would swallow the click on slower machines.
function Header({ collapsed, onToggle, data, moverCount }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="w-full px-5 py-3.5 bg-gradient-to-r from-amber-50/70 to-white border-b border-slate-100 flex items-center justify-between text-left hover:from-amber-50 transition-colors"
    >
      <div className="flex items-center gap-2">
        <ChevronDown size={15} className={`text-slate-400 transition-transform ${collapsed ? '-rotate-90' : ''}`} />
        <Sparkles size={14} className="text-amber-500" />
        <h2 className="text-[11px] font-bold text-slate-500 uppercase tracking-widest">Weekly Insights</h2>
        {collapsed && moverCount > 0 && (
          <span className="ml-1 text-[10px] font-semibold text-amber-600 bg-amber-100 rounded-full px-2 py-0.5 normal-case tracking-normal">
            {moverCount} mover{moverCount === 1 ? '' : 's'}
          </span>
        )}
      </div>
      <span className="flex items-center gap-2 text-[10px] text-slate-400 normal-case tracking-normal">
        {data?.available && (
          <>
            {fmtWeek(data.prior_week)} → {fmtWeek(data.this_week)}
            {data.generated_by === 'ai' && <span className="text-amber-500 font-medium">AI brief</span>}
          </>
        )}
        {collapsed && <span className="text-slate-300">Click to expand</span>}
      </span>
    </button>
  )
}

export default function WeeklyInsights({ dateRange = {} }) {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)
  const [collapsed, setCollapsed] = useState(true)  // minimized by default
  const [selectedWeek, setSelectedWeek] = useState(null)  // null = latest week

  const drKey = JSON.stringify(dateRange)
  // When the portfolio date range changes, reset to the latest week in the new range.
  useEffect(() => { setSelectedWeek(null) }, [drKey])

  const paramKey = JSON.stringify({ ...dateRange, week: selectedWeek })
  useEffect(() => {
    let alive = true
    setLoading(true); setError(null)
    api.weeklyInsights({ ...dateRange, ...(selectedWeek ? { week: selectedWeek } : {}) })
      .then(res => { if (alive) setData(res.data) })
      .catch(err => { if (alive) setError(err?.response?.data?.detail || err?.message || String(err)) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [paramKey])

  // Count of flagged movers — shown as a badge when collapsed
  const moverCount = data?.available
    ? data.hotels.declines.length + data.vendors.declines.length +
      data.hotels.growth.length + data.vendors.growth.length
    : 0

  const header = (
    <Header collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} data={data} moverCount={moverCount} />
  )

  if (loading) {
    return (
      <section className="rounded-2xl border border-slate-200/80 bg-white/60 shadow-sm overflow-hidden">
        {header}
        {!collapsed && <div className="p-5 text-xs text-slate-400">Analysing week-over-week movements…</div>}
      </section>
    )
  }

  if (error || !data?.available) {
    return (
      <section className="rounded-2xl border border-slate-200/80 bg-white/60 shadow-sm overflow-hidden">
        {header}
        {!collapsed && (
          <div className="p-5 text-xs text-slate-400">
            {error ? `Could not load insights: ${error}` : (data?.reason || 'Not enough data yet to compare weeks.')}
          </div>
        )}
      </section>
    )
  }

  const hotelDeclines  = data.hotels.declines
  const vendorDeclines = data.vendors.declines
  const hotelGrowth    = data.hotels.growth
  const vendorGrowth   = data.vendors.growth
  const noMovers = !hotelDeclines.length && !vendorDeclines.length && !hotelGrowth.length && !vendorGrowth.length

  const yoy = data.yoy || {}
  const yoyHotels  = yoy.hotels  || { declines: [], growth: [], metric: 'gmv' }
  const yoyVendors = yoy.vendors || { declines: [], growth: [], metric: 'bookings' }
  const yoyDeclineN = yoyHotels.declines.length + yoyVendors.declines.length
  const yoyGrowthN  = yoyHotels.growth.length + yoyVendors.growth.length
  const yoyShow = yoy.available && (yoyDeclineN || yoyGrowthN)

  const ft = data.first_time_hotels
  const ftDelta = ft ? ft.this - ft.prior : 0

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/60 shadow-sm overflow-hidden">
      {header}
      {!collapsed && (
      <div className="p-5 space-y-5">
        {/* Week selector */}
        {data.available_weeks?.length > 0 && (
          <div className="flex items-center gap-2">
            <label className="text-[11px] font-medium text-slate-500">Analysing week:</label>
            <select
              value={data.this_week}
              onChange={e => setSelectedWeek(e.target.value)}
              className="text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 bg-white text-slate-700 hover:border-amber-300 focus:outline-none focus:ring-1 focus:ring-amber-300 cursor-pointer"
            >
              {[...data.available_weeks].reverse().map((w, i) => (
                <option key={w} value={w}>
                  Week of {fmtWeek(w)}{i === 0 ? ' (latest)' : ''}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* First-time hotels — new-hotel onboarding headline */}
        {ft && (
          <div className="rounded-xl border border-indigo-100 bg-indigo-50/40 p-4 flex items-center gap-4">
            <span className="text-2xl leading-none">🆕</span>
            <div className="min-w-0">
              <p className="text-[11px] font-semibold text-indigo-700 uppercase tracking-wide">First-time hotels this week</p>
              <p className="text-[10px] text-slate-400">Hotels making their first-ever purchase</p>
            </div>
            <div className="ml-auto flex items-baseline gap-3 shrink-0">
              <span className="text-3xl font-bold text-indigo-700 tabular-nums leading-none">{ft.this}</span>
              <div className="text-[11px] leading-tight text-slate-500">
                <div className={ftDelta > 0 ? 'text-emerald-600 font-medium' : ftDelta < 0 ? 'text-amber-600 font-medium' : 'text-slate-400'}>
                  {ftDelta > 0 ? '↑' : ftDelta < 0 ? '↓' : '→'} vs {ft.prior} last week
                </div>
                <div>{ft.avg} avg ({ft.avg_weeks}-wk)</div>
              </div>
            </div>
          </div>
        )}

        {/* Brief */}
        <div className="rounded-xl bg-slate-50/70 border border-slate-100 p-4">
          <Brief narrative={data.narrative} />
        </div>

        {!noMovers && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Declines */}
            <div className="rounded-xl border border-red-100 bg-red-50/30 p-4">
              <div className="flex items-center gap-1.5 mb-2">
                <TrendingDown size={14} className="text-red-500" />
                <p className="text-xs font-semibold text-red-600 uppercase tracking-wide">Declines to investigate</p>
              </div>
              {(hotelDeclines.length || vendorDeclines.length) ? (
                <div>
                  {hotelDeclines.map((r, i) => (
                    <MoverRow key={`hd${i}`} rec={r} metric={data.hotels.metric} kind="hotel" direction="decline" />
                  ))}
                  {vendorDeclines.map((r, i) => (
                    <MoverRow key={`vd${i}`} rec={r} metric={data.vendors.metric} kind="vendor" direction="decline" />
                  ))}
                </div>
              ) : (
                <p className="text-[11px] text-slate-400 py-2">No sharp declines this week.</p>
              )}
            </div>

            {/* Growth */}
            <div className="rounded-xl border border-emerald-100 bg-emerald-50/30 p-4">
              <div className="flex items-center gap-1.5 mb-2">
                <TrendingUp size={14} className="text-emerald-500" />
                <p className="text-xs font-semibold text-emerald-700 uppercase tracking-wide">Strong growth</p>
              </div>
              {(hotelGrowth.length || vendorGrowth.length) ? (
                <div>
                  {hotelGrowth.map((r, i) => (
                    <MoverRow key={`hg${i}`} rec={r} metric={data.hotels.metric} kind="hotel" direction="growth" />
                  ))}
                  {vendorGrowth.map((r, i) => (
                    <MoverRow key={`vg${i}`} rec={r} metric={data.vendors.metric} kind="vendor" direction="growth" />
                  ))}
                </div>
              ) : (
                <p className="text-[11px] text-slate-400 py-2">No standout growth this week.</p>
              )}
            </div>
          </div>
        )}

        {/* ── Year-on-year subsection — same week last season ──────────────── */}
        {yoyShow && (
          <div className="rounded-xl border border-amber-100 bg-amber-50/20 p-4">
            <div className="flex items-center gap-1.5 mb-1">
              <Sparkles size={13} className="text-amber-500" />
              <p className="text-xs font-semibold text-amber-700 uppercase tracking-wide">Vs last season (year-on-year)</p>
            </div>
            <p className="text-[10px] text-slate-400 mb-3">
              Hotel GMV &amp; vendor bookings this week vs the same week last year ({fmtWeek(yoy.ly_week)}).
            </p>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div>
                <p className="text-[10px] font-semibold text-red-500 uppercase tracking-wide mb-1">Down vs last season</p>
                {yoyDeclineN ? (
                  <div>
                    {yoyHotels.declines.map((r, i) => (
                      <MoverRow key={`yhd${i}`} rec={r} metric={yoyHotels.metric} kind="hotel" direction="decline" />
                    ))}
                    {yoyVendors.declines.map((r, i) => (
                      <MoverRow key={`yvd${i}`} rec={r} metric={yoyVendors.metric} kind="vendor" direction="decline" />
                    ))}
                  </div>
                ) : (
                  <p className="text-[11px] text-slate-400 py-2">Nothing down vs last season.</p>
                )}
              </div>
              <div>
                <p className="text-[10px] font-semibold text-emerald-600 uppercase tracking-wide mb-1">Up vs last season</p>
                {yoyGrowthN ? (
                  <div>
                    {yoyHotels.growth.map((r, i) => (
                      <MoverRow key={`yhg${i}`} rec={r} metric={yoyHotels.metric} kind="hotel" direction="growth" />
                    ))}
                    {yoyVendors.growth.map((r, i) => (
                      <MoverRow key={`yvg${i}`} rec={r} metric={yoyVendors.metric} kind="vendor" direction="growth" />
                    ))}
                  </div>
                ) : (
                  <p className="text-[11px] text-slate-400 py-2">Nothing up vs last season.</p>
                )}
              </div>
            </div>
          </div>
        )}

        <p className="text-[10px] text-slate-400">
          Compares the latest completed week vs the prior week and the trailing {data.avg_weeks}-week average
          {yoy.available ? ', plus the same week last season (year-on-year)' : ''} ·
          excludes Cancelled bookings · low-volume movers filtered out to reduce noise.
        </p>
      </div>
      )}
    </section>
  )
}
