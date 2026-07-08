import { X } from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'

const FORECAST_COLOUR = '#6366f1'   // indigo — forecast line
const ACTUAL_COLOUR   = '#10b981'   // green  — actual line

function fmtBookings(n) {
  if (n == null) return '—'
  return Number(n).toLocaleString()
}

function fmtGMV(n) {
  if (n == null) return '—'
  return `€${Number(n).toLocaleString('en-EU', { maximumFractionDigits: 0 })}`
}

function pctStatus(forecast, actual) {
  if (actual == null || forecast == null || forecast === 0) return null
  const pct = ((actual - forecast) / forecast) * 100
  return parseFloat(pct.toFixed(1))
}

function PctCell({ forecast, actual }) {
  const pct = pctStatus(forecast, actual)
  if (pct == null) return <td className="px-3 py-2 text-slate-300 text-center">—</td>
  if (pct === 0) return <td className="px-3 py-2 text-slate-500 text-center">On target</td>
  const isExceeded = pct > 0
  return (
    <td className={`px-3 py-2 text-center font-semibold text-xs ${isExceeded ? 'text-emerald-600' : 'text-red-500'}`}>
      {Math.abs(pct).toFixed(1)}%{' '}
      <span className="font-normal">{isExceeded ? 'exceeded' : 'off'}</span>
    </td>
  )
}

function ChartTooltip({ active, payload, label, isGMV }) {
  if (!active || !payload?.length) return null
  const fmt = isGMV ? fmtGMV : fmtBookings
  const fc  = payload.find(p => p.dataKey === 'forecast')
  const ac  = payload.find(p => p.dataKey === 'actual')
  const pct = fc && ac && ac.value != null ? pctStatus(fc.value, ac.value) : null
  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-lg px-3 py-2.5 text-xs min-w-[160px]">
      <p className="font-semibold text-slate-700 mb-1.5">{label}</p>
      {fc && <p style={{ color: FORECAST_COLOUR }}>Forecast: <strong>{fmt(fc.value)}</strong></p>}
      {ac && <p style={{ color: ACTUAL_COLOUR }}>
        Actual: <strong>{ac.value != null ? fmt(ac.value) : '—'}</strong>
      </p>}
      {pct != null && (
        <p className={`mt-1 font-medium ${pct >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
          {pct >= 0 ? '▲' : '▼'} {Math.abs(pct).toFixed(1)}% {pct >= 0 ? 'exceeded' : 'off'}
        </p>
      )}
    </div>
  )
}

export default function ForecastModal({ metric, data, onClose }) {
  if (!metric || !data) return null

  const isGMV  = metric === 'gmv'
  const title  = isGMV ? 'GMV Forecast vs Actual' : 'Bookings Forecast vs Actual'
  const fmt    = isGMV ? fmtGMV : fmtBookings
  const fmtAx  = isGMV
    ? n => `€${n >= 1000 ? `${(n / 1000).toFixed(0)}k` : n}`
    : n => n >= 1000 ? `${(n / 1000).toFixed(1)}k` : n

  const weeks      = data.filter(w => w.forecast != null)
  const withActual = weeks.filter(w => w.actual != null)
  const latestActual = withActual[withActual.length - 1] ?? null

  // Chart data — null actual values kept for connect-through; use undefined to break line
  const chartData = weeks.map(w => ({
    week:     w.week,
    forecast: w.forecast,
    actual:   w.actual ?? undefined,
  }))

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl flex flex-col"
        onClick={e => e.stopPropagation()}
        style={{ maxHeight: '92vh' }}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-5 py-4 border-b border-slate-100 shrink-0">
          <div>
            <h3 className="font-bold text-slate-800 text-base">{title}</h3>
            <p className="text-xs text-slate-400 mt-0.5">
              {weeks.length} weeks with forecast · {withActual.length} weeks with actual data
            </p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors">
            <X size={15} />
          </button>
        </div>

        {/* Summary chips — latest week only */}
        {latestActual && (
          <div className="px-5 py-3 border-b border-slate-100 bg-slate-50/60 shrink-0">
            <Chip
              label="Latest week"
              value={`${fmt(latestActual.actual)} actual vs ${fmt(latestActual.forecast)} forecast`}
              colour="slate"
            />
          </div>
        )}

        {weeks.length === 0 ? (
          <div className="px-5 py-10 text-center text-slate-400 text-sm">
            No forecast data available. Check that the Forecast tab has data in rows 2–8.
          </div>
        ) : (
          <>
            {/* Line Chart */}
            <div className="px-4 py-4 shrink-0">
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis
                    dataKey="week"
                    tick={{ fontSize: 10, fill: '#94a3b8' }}
                    axisLine={false} tickLine={false}
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    tickFormatter={fmtAx}
                    tick={{ fontSize: 10, fill: '#94a3b8' }}
                    axisLine={false} tickLine={false} width={52}
                  />
                  <Tooltip content={<ChartTooltip isGMV={isGMV} />} />
                  <Legend
                    wrapperStyle={{ fontSize: 11, paddingTop: 4 }}
                    formatter={val => val === 'forecast' ? 'Forecast' : 'Actual'}
                  />
                  <Line
                    dataKey="forecast" name="forecast"
                    stroke={FORECAST_COLOUR} strokeWidth={2} strokeDasharray="5 3"
                    dot={{ r: 3, fill: FORECAST_COLOUR, strokeWidth: 0 }}
                    activeDot={{ r: 5 }} connectNulls
                  />
                  <Line
                    dataKey="actual" name="actual"
                    stroke={ACTUAL_COLOUR} strokeWidth={2.5}
                    dot={{ r: 4, fill: ACTUAL_COLOUR, strokeWidth: 0 }}
                    activeDot={{ r: 6 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* Table */}
            <div className="flex-1 overflow-y-auto border-t border-slate-100">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-slate-50 z-10">
                  <tr className="text-xs text-slate-500 uppercase tracking-wide">
                    <th className="px-3 py-2.5 text-left">Week</th>
                    <th className="px-3 py-2.5 text-right">Forecast</th>
                    <th className="px-3 py-2.5 text-right">Actual</th>
                    <th className="px-3 py-2.5 text-center">Variance</th>
                  </tr>
                </thead>
                <tbody>
                  {weeks.map((w, i) => {
                    const pct    = pctStatus(w.forecast, w.actual)
                    const hasAct = w.actual != null
                    const rowClr = !hasAct ? '' : pct == null ? '' : pct >= 0 ? 'bg-emerald-50/60' : 'bg-red-50/40'
                    return (
                      <tr key={i} className={`border-t border-slate-50 text-xs ${rowClr}`}>
                        <td className="px-3 py-2 text-slate-600 font-medium">{w.week}</td>
                        <td className="px-3 py-2 text-right text-slate-700">{fmt(w.forecast)}</td>
                        <td className={`px-3 py-2 text-right ${hasAct ? 'text-slate-800 font-medium' : 'text-slate-300'}`}>
                          {hasAct ? fmt(w.actual) : '—'}
                        </td>
                        <PctCell forecast={w.forecast} actual={w.actual} />
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}

        {/* Footer */}
        <div className="px-5 py-3 border-t border-slate-100 bg-slate-50/60 shrink-0">
          <p className="text-[10px] text-slate-400">
            Source: Forecast tab · Dashed indigo = forecast target · Solid green = actual recorded ·
            {isGMV ? ' GMV in €' : ' Bookings = paid transactions'} · Click outside to close
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
