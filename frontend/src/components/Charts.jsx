import {
  AreaChart, Area, BarChart, Bar, LineChart, Line, ComposedChart,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, Cell,
} from 'recharts'

const fmtEur   = v => `€${Number(v).toLocaleString('en-EU', { maximumFractionDigits: 0 })}`
const fmtPct   = v => `${Number(v).toFixed(1)}%`
const fmtNum   = v => Number(v).toLocaleString()

// Y-axis euro formatter that adapts to magnitude. Values in the hundreds show
// as exact euros (€300) instead of collapsing to "€0k"; thousands use "k" with
// one decimal where needed (€1.5k) so ticks never round to the same label.
const fmtAxisEur = v => {
  if (!v) return '€0'
  const abs = Math.abs(v)
  if (abs >= 1000) {
    const k = v / 1000
    return `€${Number.isInteger(k) ? k : k.toFixed(1)}k`
  }
  return `€${Math.round(v)}`
}

// Axis tick: "12 May" — short, avoids crowding
const fmtDate  = d => {
  if (!d) return ''
  const dt = new Date(d + 'T00:00:00')
  return dt.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

// Tooltip header: "Week of 12 May 2025" — includes year for clarity
const fmtDateFull = d => {
  if (!d) return ''
  const dt = new Date(d + 'T00:00:00')
  return `Week of ${dt.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}`
}

const SNAPSHOT_NOTE = 'Each data point = that week only. Weekly snapshot — not cumulative. · Date shown = week start (Monday)'

const C = {
  gmv:          '#3b82f6',
  net_revenue:  '#10b981',
  aov:          '#f59e0b',
  attach_rate:  '#ec4899',
  active_hotels:'#8b5cf6',
  transactions: '#64748b',
}

function ChartCard({ title, note, children }) {
  return (
    <div className="card p-4">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">{title}</p>
      {children}
      <p className="text-[10px] text-slate-400 mt-1.5 leading-tight">{note ?? SNAPSHOT_NOTE}</p>
    </div>
  )
}

const hasPrevYear = data => data.some(d => d.prev_gmv != null || d.prev_net_revenue != null)

const PrevYearLabel = () => (
  <span style={{ color: '#94a3b8', fontSize: 11 }}>— Prior year (same week)</span>
)

/* ── 1a. GMV ───────────────────────────────────────────────────────────────── */
export function GMVChart({ data }) {
  const showPrev = hasPrevYear(data)
  return (
    <ChartCard title="GMV (Gross Merchandise Value) — Per Week">
      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="gGmv" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor={C.gmv} stopOpacity={0.18} />
              <stop offset="95%" stopColor={C.gmv} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="week_start_date" tickFormatter={fmtDate} tick={{ fontSize: 10 }} />
          <YAxis tickFormatter={fmtAxisEur} tick={{ fontSize: 10 }} width={48} />
          <Tooltip
            formatter={(v, name) => [fmtEur(v), name === 'prev_gmv' ? 'GMV (prior year)' : 'GMV']}
            labelFormatter={fmtDateFull}
          />
          {showPrev && <Legend formatter={v => v === 'prev_gmv' ? 'Prior year' : 'This year'} wrapperStyle={{ fontSize: 11 }} />}
          <Area type="monotone" dataKey="gmv" name="gmv" stroke={C.gmv} fill="url(#gGmv)" strokeWidth={2} dot={false} />
          {showPrev && (
            <Line type="monotone" dataKey="prev_gmv" name="prev_gmv"
              stroke="#94a3b8" strokeWidth={1.5} strokeDasharray="4 3"
              dot={false} connectNulls />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

/* ── 1b. Net Revenue ───────────────────────────────────────────────────────── */
export function NetRevenueChart({ data }) {
  const showPrev = hasPrevYear(data)
  return (
    <ChartCard title="BG Net Revenue — Per Week">
      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="gRev" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor={C.net_revenue} stopOpacity={0.18} />
              <stop offset="95%" stopColor={C.net_revenue} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="week_start_date" tickFormatter={fmtDate} tick={{ fontSize: 10 }} />
          <YAxis tickFormatter={fmtAxisEur} tick={{ fontSize: 10 }} width={48} />
          <Tooltip
            formatter={(v, name) => [fmtEur(v), name === 'prev_net_revenue' ? 'Net Rev (prior year)' : 'Net Revenue']}
            labelFormatter={fmtDateFull}
          />
          {showPrev && <Legend formatter={v => v === 'prev_net_revenue' ? 'Prior year' : 'This year'} wrapperStyle={{ fontSize: 11 }} />}
          <Area type="monotone" dataKey="net_revenue" name="net_revenue" stroke={C.net_revenue} fill="url(#gRev)" strokeWidth={2} dot={false} />
          {showPrev && (
            <Line type="monotone" dataKey="prev_net_revenue" name="prev_net_revenue"
              stroke="#94a3b8" strokeWidth={1.5} strokeDasharray="4 3"
              dot={false} connectNulls />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

/* ── 2. AOV ────────────────────────────────────────────────────────────────── */
export function AOVChart({ data }) {
  return (
    <ChartCard title="Average Order Value (AOV) — Per Week">
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="week_start_date" tickFormatter={fmtDate} tick={{ fontSize: 10 }} />
          <YAxis tickFormatter={v => `€${v}`} tick={{ fontSize: 10 }} width={44} />
          <Tooltip formatter={v => [fmtEur(v), 'AOV']} labelFormatter={fmtDateFull} />
          <Line type="monotone" dataKey="aov" stroke={C.aov} strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

/* ── 3. Attach Rate ────────────────────────────────────────────────────────── */
export function AttachRateChart({ data }) {
  return (
    <ChartCard
      title="Attach Rate — Weekly Snapshot (paid bookings ÷ active-hotel rooms)"
      note="Each point = that week's paid bookings ÷ rooms across active hotels that week. Weekly snapshot — not cumulative. · Date shown = week start (Monday)"
    >
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="week_start_date" tickFormatter={fmtDate} tick={{ fontSize: 10 }} />
          <YAxis tickFormatter={fmtPct} tick={{ fontSize: 10 }} width={44} />
          <Tooltip
            formatter={v => [fmtPct(v), 'Attach Rate (that week only)']}
            labelFormatter={d => `${fmtDateFull(d)} — weekly snapshot, not cumulative`}
          />
          <Line type="monotone" dataKey="attach_rate" stroke={C.attach_rate} strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

/* ── 4. Active Hotels ──────────────────────────────────────────────────────── */
export function ActiveHotelsChart({ data }) {
  return (
    <ChartCard title="Active Hotels — Weekly Snapshot">
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="week_start_date" tickFormatter={fmtDate} tick={{ fontSize: 10 }} />
          <YAxis tick={{ fontSize: 10 }} width={30} allowDecimals={false} />
          <Tooltip formatter={v => [v, 'Hotels']} labelFormatter={fmtDateFull} />
          <Bar dataKey="active_hotels" fill={C.active_hotels} radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

/* ── 5b. Average Cart Value by Hotel ──────────────────────────────────────── */
const CLASS_BAR_COLOUR = { A: '#3b82f6', B: '#10b981', C: '#f59e0b' }

export function HotelAOVChart({ hotels }) {
  const data = [...hotels]
    .filter(h => h.aov > 0)
    .sort((a, b) => b.aov - a.aov)
    .map(h => ({ name: h.hotel_name, aov: h.aov, fill: CLASS_BAR_COLOUR[h.activity_class] || '#94a3b8' }))

  if (!data.length) return null

  const barHeight = 22
  const chartHeight = Math.max(160, data.length * barHeight + 40)
  // Truncate long names for the Y-axis tick
  const truncate = str => str.length > 22 ? str.slice(0, 20) + '…' : str

  return (
    <ChartCard
      title="Average Cart Value (AOV) — by Hotel"
      note="Sorted highest to lowest. Colour = activity class: blue A · green B · amber C · grey inactive."
    >
      <ResponsiveContainer width="100%" height={chartHeight}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 48, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
          <XAxis type="number" tickFormatter={v => `€${v}`} tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis type="category" dataKey="name" tickFormatter={truncate} tick={{ fontSize: 10 }} width={130} axisLine={false} tickLine={false} />
          <Tooltip formatter={v => [fmtEur(v), 'AOV']} />
          <Bar dataKey="aov" radius={[0, 3, 3, 0]} maxBarSize={18}>
            {data.map((entry, i) => (
              <Cell key={i} fill={entry.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

/* ── 5. Paid Transactions & Cancellations ─────────────────────────────────── */
const CANCEL_COLOUR = '#ef4444'

function TransactionsTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const paid = payload.find(p => p.dataKey === 'transactions')
  const cancelled = payload.find(p => p.dataKey === 'cancellations')
  const rate = payload.find(p => p.dataKey === 'cancellation_rate')
  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-lg px-3 py-2.5 text-xs">
      <p className="font-semibold text-slate-700 mb-1">{fmtDateFull(label)}</p>
      {paid && <p style={{ color: C.gmv }}>Paid Bookings: <strong>{fmtNum(paid.value)}</strong></p>}
      {cancelled && cancelled.value != null && (
        <p style={{ color: CANCEL_COLOUR }}>Cancellations: <strong>{fmtNum(cancelled.value)}</strong></p>
      )}
      {rate && rate.value != null && (
        <p style={{ color: CANCEL_COLOUR }}>Cancellation Rate: <strong>{fmtPct(rate.value)}</strong></p>
      )}
    </div>
  )
}

export function TransactionsChart({ data }) {
  const hasCancellations = data.some(d => d.cancellations != null)
  return (
    <ChartCard
      title={hasCancellations
        ? 'Paid Bookings vs Cancellations — Weekly Snapshot'
        : 'Paid Transactions — Weekly Snapshot'}
      note={hasCancellations
        ? 'Blue bars = paid bookings that week · Red bars = cancelled bookings that week · Red line = week’s cancellation rate (right axis) · Not cumulative · Date shown = week start (Monday)'
        : SNAPSHOT_NOTE}
    >
      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={data} margin={{ top: 4, right: hasCancellations ? 36 : 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="week_start_date" tickFormatter={fmtDate} tick={{ fontSize: 10 }} />
          <YAxis yAxisId="left" tick={{ fontSize: 10 }} width={35} allowDecimals={false} />
          {hasCancellations && (
            <YAxis yAxisId="right" orientation="right" tickFormatter={fmtPct}
              tick={{ fontSize: 10, fill: CANCEL_COLOUR }} width={42} />
          )}
          <Tooltip content={<TransactionsTooltip />} />
          <Legend
            formatter={v => {
              if (v === 'transactions')       return 'Paid Bookings'
              if (v === 'cancellations')       return 'Cancellations'
              if (v === 'cancellation_rate')   return 'Cancellation Rate %'
              return v
            }}
            wrapperStyle={{ fontSize: 11 }}
          />
          <Bar yAxisId="left" dataKey="transactions" name="transactions" fill={C.gmv} radius={[3, 3, 0, 0]} />
          {hasCancellations && (
            <Bar yAxisId="left" dataKey="cancellations" name="cancellations" fill={CANCEL_COLOUR} radius={[3, 3, 0, 0]} />
          )}
          {hasCancellations && (
            <Line yAxisId="right" type="monotone" dataKey="cancellation_rate" name="cancellation_rate"
              stroke={CANCEL_COLOUR} strokeWidth={2}
              dot={{ r: 2.5, fill: CANCEL_COLOUR, strokeWidth: 0 }} activeDot={{ r: 4 }}
              connectNulls />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}
