import { useState } from 'react'
import { X, TrendingUp, TrendingDown, Minus } from 'lucide-react'
import {
  ComposedChart, LineChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'

// Class colours shared across stacked metrics
const CLASS_COLOURS = { A: '#3b82f6', B: '#10b981', C: '#f59e0b' }

// ── Attach Rate helpers ──────────────────────────────────────────────────────

const ATTACH_LINES = [
  { key: 'rate_a',   label: 'Class A only',        colour: '#3b82f6' },
  { key: 'rate_ab',  label: 'Class A+B (incl. A)', colour: '#10b981' },
  { key: 'rate_abc', label: 'All Active (A+B+C)',   colour: '#ec4899' },
]

function buildWeeklyAttach(trendData) {
  return trendData.map(pt => ({
    label:    fmtWeek(pt.week_start_date),
    rate_a:   pt.attach_rate_class_a  ?? 0,
    rate_ab:  pt.attach_rate_class_ab ?? 0,
    rate_abc: pt.attach_rate          ?? 0,
  }))
}

function buildMonthlyAttach(trendData) {
  const byMonth = {}
  trendData.forEach(pt => {
    const key = pt.week_start_date.slice(0, 7)
    if (!byMonth[key]) byMonth[key] = {
      txns_a: 0, txns_ab: 0, txns_abc: 0,
      rooms_a: [], rooms_ab: [], rooms_abc: [],
    }
    byMonth[key].txns_a   += pt.txns_class_a  ?? 0
    byMonth[key].txns_ab  += pt.txns_class_ab ?? 0
    byMonth[key].txns_abc += pt.transactions   ?? 0
    byMonth[key].rooms_a.push(pt.rooms_class_a ?? 0)
    byMonth[key].rooms_ab.push((pt.rooms_class_a ?? 0) + (pt.rooms_class_b ?? 0))
    byMonth[key].rooms_abc.push(pt.rooms_live ?? 0)
  })
  const avg = arr => arr.length ? arr.reduce((s, v) => s + v, 0) / arr.length : 0
  return Object.entries(byMonth)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, d]) => {
      const rA   = avg(d.rooms_a)
      const rAB  = avg(d.rooms_ab)
      const rABC = avg(d.rooms_abc)
      return {
        label:    new Date(key + '-01').toLocaleDateString('en-GB', { month: 'short', year: '2-digit' }),
        rate_a:   rA   > 0 ? parseFloat((d.txns_a   / rA   * 100).toFixed(2)) : 0,
        rate_ab:  rAB  > 0 ? parseFloat((d.txns_ab  / rAB  * 100).toFixed(2)) : 0,
        rate_abc: rABC > 0 ? parseFloat((d.txns_abc / rABC * 100).toFixed(2)) : 0,
      }
    })
}

function buildMonthlyData(trendData, field) {
  const byMonth = {}
  trendData.forEach(pt => {
    const key = pt.week_start_date.slice(0, 7)
    byMonth[key] = (byMonth[key] ?? 0) + (pt[field] ?? 0)
  })
  const entries = Object.entries(byMonth).sort(([a], [b]) => a.localeCompare(b))
  return entries.map(([key, value], i) => {
    const prev = i > 0 ? entries[i - 1][1] : null
    const mom  = prev != null && prev > 0
      ? parseFloat(((value - prev) / prev * 100).toFixed(1))
      : null
    return {
      month: new Date(key + '-01').toLocaleDateString('en-GB', { month: 'short', year: '2-digit' }),
      value: parseFloat(value.toFixed(2)),
      mom,
    }
  })
}

function AttachTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-lg px-3 py-2.5 text-xs">
      <p className="font-semibold text-slate-700 mb-1">{label}</p>
      {payload.map(p => (
        <p key={p.dataKey} style={{ color: p.color }}>
          {p.name}: <strong>{Number(p.value).toFixed(2)}%</strong>
        </p>
      ))}
    </div>
  )
}

// ── Metric config: which field to read from trend point + display helpers ───
const METRIC_CONFIG = {
  active_hotels: {
    label:      'Active Hotels',
    field:      'active_hotels',
    lineColour: '#a855f7',
    formatVal:  n => String(n),
    formatAxis: n => n,
    unit: 'hotels',
    stacked: true,
    fieldA: 'active_hotels_class_a',
    fieldB: 'active_hotels_class_b',
    fieldC: 'active_hotels_class_c',
  },
  rooms_live: {
    label:      'Rooms Live',
    field:      'rooms_live',
    lineColour: '#a855f7',
    formatVal:  n => Number(n).toLocaleString(),
    formatAxis: n => n >= 1000 ? `${(n/1000).toFixed(1)}k` : n,
    unit: 'rooms',
    stacked: true,
    fieldA: 'rooms_class_a',
    fieldB: 'rooms_class_b',
    fieldC: 'rooms_class_c',
  },
  net_revenue: {
    label:      'BG Net Revenue',
    field:      'net_revenue',
    prevField:  'prev_net_revenue',   // same week last season, 364 days back
    barColour:  '#10b981',
    lineColour: '#f59e0b',
    prevColour: '#94a3b8',
    formatVal:  n => `€${Number(n).toLocaleString('en-EU', { maximumFractionDigits: 0 })}`,
    formatAxis: n => `€${n >= 1000 ? `${(n/1000).toFixed(0)}k` : n}`,
    unit: '€',
    footerNote: 'Bars = weekly Net Revenue · Yellow line = week-on-week % change · Grey dashed line = same week last season · Date shown = week start (Monday) · Click outside to close',
  },
  attach_rate: {
    label:      'Attach Rate',
    field:      'attach_rate',
    formatVal:  n => `${Number(n).toFixed(2)}%`,
    formatAxis: n => `${n}%`,
    unit:       '%',
    multiLine:  true,   // signals 3-line chart with week/month toggle
  },
  gmv: {
    label:      'GMV',
    field:      'gmv',
    barColour:  '#6366f1',
    lineColour: '#f59e0b',
    formatVal:  n => `€${Number(n).toLocaleString('en-EU', { maximumFractionDigits: 0 })}`,
    formatAxis: n => `€${n >= 1000 ? `${(n/1000).toFixed(0)}k` : n}`,
    unit: '€',
  },
  aov: {
    label:      'Average Order Value',
    field:      'aov',
    barColour:  '#0ea5e9',
    lineColour: '#f59e0b',
    formatVal:  n => `€${Number(n).toLocaleString('en-EU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
    formatAxis: n => `€${n}`,
    unit:       '€',
    footerNote: 'AOV = weekly GMV ÷ paid bookings that week · Yellow line = week-on-week % change · Click outside to close',
  },
  alsabini: {
    label:      'Alsabini Revenue',
    field:      'alsabini_revenue',
    barColour:  '#f59e0b',
    lineColour: '#f59e0b',
    formatVal:  n => `€${Number(n).toLocaleString('en-EU', { maximumFractionDigits: 0 })}`,
    formatAxis: n => `€${n >= 1000 ? `${(n/1000).toFixed(0)}k` : n}`,
    unit: '€',
    footerNote: 'Bars = weekly Alsabini Take (revenue) · Yellow line = week-on-week % change · Date shown = week start (Monday) · Click outside to close',
  },
  mnr: {
    label:      'Monthly Net Revenue (MNR)',
    field:      'net_revenue',
    barColour:  '#10b981',
    lineColour: '#f59e0b',
    formatVal:  n => `€${Number(n).toLocaleString('en-EU', { maximumFractionDigits: 0 })}`,
    formatAxis: n => `€${n >= 1000 ? `${(n/1000).toFixed(0)}k` : n}`,
    unit:       '€',
    monthly:    true,   // aggregate weekly net_revenue into calendar months
    footerNote: 'Bars = sum of weekly net revenue in that calendar month · Orange line = month-on-month % change · Click outside to close',
  },
}

function fmtWeek(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('en-GB', { month: 'short', day: 'numeric' })
}

function CustomTooltip({ active, payload, label, cfg }) {
  if (!active || !payload?.length) return null
  const wow = payload.find(p => p.dataKey === 'wow')

  if (cfg.stacked) {
    const a = payload.find(p => p.dataKey === 'class_a')
    const b = payload.find(p => p.dataKey === 'class_b')
    const c = payload.find(p => p.dataKey === 'class_c')
    const total = (a?.value ?? 0) + (b?.value ?? 0) + (c?.value ?? 0)
    return (
      <div className="bg-white border border-slate-200 rounded-xl shadow-lg px-3 py-2.5 text-xs">
        <p className="font-semibold text-slate-700 mb-1">{label}</p>
        {a && <p style={{ color: CLASS_COLOURS.A }}>Class A: <strong>{cfg.formatVal(a.value)}</strong></p>}
        {b && <p style={{ color: CLASS_COLOURS.B }}>Class B: <strong>{cfg.formatVal(b.value)}</strong></p>}
        {c && <p style={{ color: CLASS_COLOURS.C }}>Class C: <strong>{cfg.formatVal(c.value)}</strong></p>}
        <p className="text-slate-500 border-t border-slate-100 mt-1 pt-1">Total: <strong>{cfg.formatVal(total)}</strong></p>
        {wow && wow.value != null && (
          <p style={{ color: wow.value >= 0 ? '#10b981' : '#ef4444' }}>
            WoW: <strong>{wow.value > 0 ? '+' : ''}{wow.value.toFixed(1)}%</strong>
          </p>
        )}
      </div>
    )
  }

  const val        = payload.find(p => p.dataKey === 'value')
  const lastSeason = payload.find(p => p.dataKey === 'lastSeason')
  const vsLastSeasonPct = (lastSeason && lastSeason.value != null && lastSeason.value > 0 && val)
    ? ((val.value - lastSeason.value) / lastSeason.value * 100)
    : null
  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-lg px-3 py-2.5 text-xs">
      <p className="font-semibold text-slate-700 mb-1">{label}</p>
      {val && <p style={{ color: cfg.barColour }}>{cfg.label}: <strong>{cfg.formatVal(val.value)}</strong></p>}
      {wow && wow.value != null && (
        <p style={{ color: wow.value >= 0 ? '#10b981' : '#ef4444' }}>
          WoW: <strong>{wow.value > 0 ? '+' : ''}{wow.value.toFixed(1)}%</strong>
        </p>
      )}
      {lastSeason && lastSeason.value != null && (
        <p style={{ color: cfg.prevColour || '#94a3b8' }}>
          Last season: <strong>{cfg.formatVal(lastSeason.value)}</strong>
          {vsLastSeasonPct != null && (
            <span> ({vsLastSeasonPct >= 0 ? '+' : ''}{vsLastSeasonPct.toFixed(1)}%)</span>
          )}
        </p>
      )}
    </div>
  )
}

export default function DrillDownModal({ metric, trendData, onClose, dateRange = {}, filters = {} }) {
  const [attachView, setAttachView] = useState('week')   // 'week' | 'month'

  if (!metric || !trendData?.length) return null

  const cfg = METRIC_CONFIG[metric]
  if (!cfg) return null

  // ── Attach Rate: multi-line chart with week/month toggle ─────────────────
  if (cfg.multiLine) {
    const chartData = attachView === 'month'
      ? buildMonthlyAttach(trendData)
      : buildWeeklyAttach(trendData)

    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
        onClick={onClose}
      >
        <div
          className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl flex flex-col"
          onClick={e => e.stopPropagation()}
          style={{ maxHeight: '90vh' }}
        >
          {/* Header */}
          <div className="flex items-start justify-between px-5 py-4 border-b border-slate-100">
            <div>
              <h3 className="font-bold text-slate-800 text-base">{cfg.label} — by Active Hotel Class</h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Class A only · Class A+B inclusive · All Active (A+B+C) · {trendData.length} weeks of data
              </p>
            </div>
            <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors">
              <X size={15} />
            </button>
          </div>

          {/* Week / Month toggle */}
          <div className="px-5 pt-3 pb-1 flex gap-2">
            {['week', 'month'].map(v => (
              <button
                key={v}
                onClick={() => setAttachView(v)}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  attachView === v
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'bg-white border border-slate-200 text-slate-600 hover:border-blue-300 hover:text-blue-600'
                }`}
              >
                {v === 'week' ? 'Weekly' : 'Monthly'}
              </button>
            ))}
          </div>

          {/* Chart */}
          <div className="px-4 py-3 flex-1 overflow-hidden">
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
                <YAxis
                  tickFormatter={n => `${n}%`}
                  tick={{ fontSize: 11, fill: '#94a3b8' }}
                  axisLine={false} tickLine={false} width={44}
                />
                <Tooltip content={<AttachTooltip />} />
                <Legend
                  wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
                  formatter={val => ATTACH_LINES.find(l => l.key === val)?.label ?? val}
                />
                {ATTACH_LINES.map(l => (
                  <Line
                    key={l.key}
                    dataKey={l.key}
                    name={l.key}
                    stroke={l.colour}
                    strokeWidth={2}
                    dot={{ r: 2, fill: l.colour, strokeWidth: 0 }}
                    activeDot={{ r: 4 }}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Footer */}
          <div className="px-5 py-3 border-t border-slate-100 bg-slate-50/60">
            <p className="text-[10px] text-slate-400">
              {attachView === 'week'
                ? 'Each point = paid bookings ÷ rooms for that class that week · Date shown = week start (Monday) · Click outside to close'
                : 'Each point = total monthly bookings ÷ avg weekly rooms for that class that month · Click outside to close'}
            </p>
          </div>
        </div>
      </div>
    )
  }

  // ── Monthly aggregation path ─────────────────────────────────────────────
  if (cfg.monthly) {
    const monthlyData = buildMonthlyData(trendData, cfg.field)
    const mValues     = monthlyData.map(d => d.value)
    const mLatest     = mValues[mValues.length - 1]
    const mFirst      = mValues[0]
    const mOverall    = mFirst > 0 ? ((mLatest - mFirst) / mFirst * 100).toFixed(1) : null
    const mMoMs       = monthlyData.map(d => d.mom).filter(v => v != null)
    const mAvgMoM     = mMoMs.length ? (mMoMs.reduce((a, b) => a + b, 0) / mMoMs.length).toFixed(1) : null
    const MTrendIcon  = mOverall == null ? Minus : mOverall >= 0 ? TrendingUp : TrendingDown
    const mTrendClr   = mOverall == null ? 'text-slate-400' : mOverall >= 0 ? 'text-emerald-500' : 'text-red-500'

    function MoMTooltip({ active, payload, label: lbl }) {
      if (!active || !payload?.length) return null
      const val = payload.find(p => p.dataKey === 'value')
      const mom = payload.find(p => p.dataKey === 'mom')
      return (
        <div className="bg-white border border-slate-200 rounded-xl shadow-lg px-3 py-2.5 text-xs">
          <p className="font-semibold text-slate-700 mb-1">{lbl}</p>
          {val && <p style={{ color: cfg.barColour }}>{cfg.label}: <strong>{cfg.formatVal(val.value)}</strong></p>}
          {mom && mom.value != null && (
            <p style={{ color: mom.value >= 0 ? '#10b981' : '#ef4444' }}>
              MoM: <strong>{mom.value > 0 ? '+' : ''}{mom.value.toFixed(1)}%</strong>
            </p>
          )}
        </div>
      )
    }

    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
        onClick={onClose}
      >
        <div
          className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl flex flex-col"
          onClick={e => e.stopPropagation()}
          style={{ maxHeight: '90vh' }}
        >
          {/* Header */}
          <div className="flex items-start justify-between px-5 py-4 border-b border-slate-100">
            <div>
              <h3 className="font-bold text-slate-800 text-base">{cfg.label}</h3>
              <p className="text-xs text-slate-400 mt-0.5">Month-by-month · {monthlyData.length} months of data</p>
            </div>
            <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors">
              <X size={15} />
            </button>
          </div>

          {/* Summary chips */}
          <div className="px-5 py-3 flex flex-wrap gap-3 border-b border-slate-100 bg-slate-50/60">
            <Chip label="Latest month" value={cfg.formatVal(mLatest)} colour="slate" />
            {mOverall != null && (
              <Chip label="vs Month 1" value={`${mOverall >= 0 ? '+' : ''}${mOverall}%`} colour={mOverall >= 0 ? 'green' : 'red'} />
            )}
            {mAvgMoM != null && (
              <Chip label="Avg MoM" value={`${mAvgMoM >= 0 ? '+' : ''}${mAvgMoM}%`} colour={mAvgMoM >= 0 ? 'blue' : 'amber'} />
            )}
            <div className={`flex items-center gap-1 ${mTrendClr}`}>
              <MTrendIcon size={14} />
              <span className="text-xs font-medium">
                {mOverall != null ? `${Math.abs(mOverall)}% ${mOverall >= 0 ? 'growth' : 'decline'} overall` : 'No change'}
              </span>
            </div>
          </div>

          {/* Chart */}
          <div className="px-4 py-4 flex-1 overflow-hidden">
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={monthlyData} margin={{ top: 8, right: 45, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
                <YAxis
                  yAxisId="left"
                  tickFormatter={cfg.formatAxis}
                  tick={{ fontSize: 11, fill: '#94a3b8' }}
                  axisLine={false} tickLine={false} width={52}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  tickFormatter={n => `${n}%`}
                  tick={{ fontSize: 11, fill: cfg.lineColour }}
                  axisLine={false} tickLine={false} width={42}
                />
                <Tooltip content={<MoMTooltip />} />
                <Legend
                  wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
                  formatter={val => val === 'value' ? cfg.label : 'MoM Growth %'}
                />
                <ReferenceLine yAxisId="right" y={0} stroke="#e2e8f0" />
                <Bar yAxisId="left" dataKey="value" name="value"
                     fill={cfg.barColour} radius={[4,4,0,0]} opacity={0.85} maxBarSize={56} />
                <Line
                  yAxisId="right" dataKey="mom" name="mom"
                  stroke={cfg.lineColour} strokeWidth={2}
                  dot={{ r: 3, fill: cfg.lineColour, strokeWidth: 0 }}
                  activeDot={{ r: 5 }} connectNulls
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* Footer */}
          <div className="px-5 py-3 border-t border-slate-100 bg-slate-50/60">
            <p className="text-[10px] text-slate-400">{cfg.footerNote}</p>
          </div>
        </div>
      </div>
    )
  }

  // Build chart data with week-on-week growth
  const chartData = trendData.map((pt, i) => {
    const val  = pt[cfg.field] ?? 0
    const prev = i > 0 ? (trendData[i - 1][cfg.field] ?? 0) : null
    const wow  = prev != null && prev > 0
      ? parseFloat(((val - prev) / prev * 100).toFixed(1))
      : null
    const entry = { week: fmtWeek(pt.week_start_date), value: val, wow }
    if (cfg.stacked) {
      entry.class_a = pt[cfg.fieldA] ?? 0
      entry.class_b = pt[cfg.fieldB] ?? 0
      entry.class_c = pt[cfg.fieldC] ?? 0
    }
    if (cfg.prevField) {
      const lastSeason = pt[cfg.prevField]
      entry.lastSeason = lastSeason != null ? lastSeason : null
    }
    return entry
  })

  // Summary stats
  const values     = chartData.map(d => d.value)
  const latest     = values[values.length - 1]
  const first      = values[0]
  const overallPct = first > 0 ? ((latest - first) / first * 100).toFixed(1) : null
  const wows       = chartData.map(d => d.wow).filter(w => w != null)
  const avgWoW     = wows.length ? (wows.reduce((a, b) => a + b, 0) / wows.length).toFixed(1) : null

  const TrendIcon   = overallPct == null ? Minus : overallPct >= 0 ? TrendingUp : TrendingDown
  const trendColour = overallPct == null ? 'text-slate-400' : overallPct >= 0 ? 'text-emerald-500' : 'text-red-500'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl flex flex-col"
        onClick={e => e.stopPropagation()}
        style={{ maxHeight: '90vh' }}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-5 py-4 border-b border-slate-100">
          <div>
            <h3 className="font-bold text-slate-800 text-base">{cfg.label}</h3>
            <p className="text-xs text-slate-400 mt-0.5">Week-by-week growth · {trendData.length} weeks</p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
          >
            <X size={15} />
          </button>
        </div>

        {/* Summary chips */}
        <div className="px-5 py-3 flex flex-wrap gap-3 border-b border-slate-100 bg-slate-50/60">
          <Chip label="Latest" value={cfg.formatVal(latest)} colour="slate" />
          {overallPct != null && (
            <Chip
              label="vs Week 1"
              value={`${overallPct >= 0 ? '+' : ''}${overallPct}%`}
              colour={overallPct >= 0 ? 'green' : 'red'}
            />
          )}
          {avgWoW != null && (
            <Chip
              label="Avg WoW"
              value={`${avgWoW >= 0 ? '+' : ''}${avgWoW}%`}
              colour={avgWoW >= 0 ? 'blue' : 'amber'}
            />
          )}
          <div className={`flex items-center gap-1 ${trendColour}`}>
            <TrendIcon size={14} />
            <span className="text-xs font-medium">
              {overallPct != null ? `${Math.abs(overallPct)}% ${overallPct >= 0 ? 'growth' : 'decline'} overall` : 'No change'}
            </span>
          </div>
        </div>

        {/* Chart */}
        <div className="px-4 py-4 flex-1 overflow-hidden">
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={chartData} margin={{ top: 8, right: 45, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis
                dataKey="week"
                tick={{ fontSize: 11, fill: '#94a3b8' }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                yAxisId="left"
                tickFormatter={cfg.formatAxis}
                tick={{ fontSize: 11, fill: '#94a3b8' }}
                axisLine={false}
                tickLine={false}
                width={52}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                tickFormatter={n => `${n}%`}
                tick={{ fontSize: 11, fill: cfg.lineColour }}
                axisLine={false}
                tickLine={false}
                width={42}
              />
              <Tooltip content={<CustomTooltip cfg={cfg} />} />
              <Legend
                wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
                formatter={val => {
                  if (val === 'class_a')    return 'Class A'
                  if (val === 'class_b')    return 'Class B'
                  if (val === 'class_c')    return 'Class C'
                  if (val === 'value')      return cfg.label
                  if (val === 'lastSeason') return 'Last Season'
                  return 'WoW Growth %'
                }}
              />
              <ReferenceLine yAxisId="right" y={0} stroke="#e2e8f0" />

              {cfg.stacked ? (
                <>
                  <Bar yAxisId="left" dataKey="class_a" name="class_a" stackId="s"
                       fill={CLASS_COLOURS.A} opacity={0.85} maxBarSize={48} radius={[0,0,0,0]} />
                  <Bar yAxisId="left" dataKey="class_b" name="class_b" stackId="s"
                       fill={CLASS_COLOURS.B} opacity={0.85} maxBarSize={48} radius={[0,0,0,0]} />
                  <Bar yAxisId="left" dataKey="class_c" name="class_c" stackId="s"
                       fill={CLASS_COLOURS.C} opacity={0.85} maxBarSize={48} radius={[4,4,0,0]} />
                </>
              ) : (
                <Bar yAxisId="left" dataKey="value" name="value"
                     fill={cfg.barColour} radius={[4,4,0,0]} opacity={0.85} maxBarSize={48} />
              )}

              {cfg.prevField && (
                <Line
                  yAxisId="left"
                  dataKey="lastSeason"
                  name="lastSeason"
                  stroke={cfg.prevColour || '#94a3b8'}
                  strokeWidth={2}
                  strokeDasharray="5 4"
                  dot={{ r: 2.5, fill: cfg.prevColour || '#94a3b8', strokeWidth: 0 }}
                  activeDot={{ r: 4 }}
                  connectNulls
                />
              )}

              <Line
                yAxisId="right"
                dataKey="wow"
                name="wow"
                stroke={cfg.lineColour}
                strokeWidth={2}
                dot={{ r: 3, fill: cfg.lineColour, strokeWidth: 0 }}
                activeDot={{ r: 5 }}
                connectNulls
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-slate-100 bg-slate-50/60">
          <p className="text-[10px] text-slate-400">
            {cfg.footerNote
              ? cfg.footerNote
              : cfg.stacked
                ? `Stacked bars = Class A (blue) / B (green) / C (amber) · Purple line = week-on-week % change · Date shown = week start (Monday) · Click outside to close`
                : `Bars = weekly ${cfg.unit} · Yellow line = week-on-week % change · Date shown = week start (Monday) · Click outside to close`}
          </p>
        </div>
      </div>
    </div>
  )
}

function Chip({ label, value, colour }) {
  const colours = {
    slate: 'bg-slate-100 text-slate-600',
    green: 'bg-emerald-100 text-emerald-700',
    red:   'bg-red-100 text-red-700',
    blue:  'bg-blue-100 text-blue-700',
    amber: 'bg-amber-100 text-amber-700',
  }
  return (
    <div className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${colours[colour] || colours.slate}`}>
      <span className="opacity-60">{label}:</span>
      <span>{value}</span>
    </div>
  )
}
