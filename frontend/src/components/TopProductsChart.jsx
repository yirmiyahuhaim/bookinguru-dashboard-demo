import { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from 'recharts'
import { api } from '../api/client'

const fmtEur = v => `€${Number(v).toLocaleString('en-EU', { maximumFractionDigits: 0 })}`
const truncate = (str, n) => str && str.length > n ? str.slice(0, n - 1) + '…' : str

const fmtWeek = str => {
  if (!str) return ''
  const d = new Date(str + 'T00:00:00')
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

const fmtWeekFull = str => {
  if (!str) return ''
  const d = new Date(str + 'T00:00:00')
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

const COLOURS = [
  '#6366f1','#10b981','#f59e0b','#3b82f6','#ec4899',
  '#06b6d4','#84cc16','#f97316','#8b5cf6','#14b8a6',
]

const MIN_WEEK_PX = 64
const TOOLTIP_W   = 320
const OFFSET      = 16   // gap between cursor and tooltip edge

// Renders into document.body via a portal — escapes all overflow clipping.
// Flips left when there isn't enough space to the right of the cursor.
function PortalTooltip({ data, products }) {
  if (!data) return null

  const { x, y, week, entries } = data
  const activeEntries = [...entries]
    .filter(p => p.value > 0)
    .sort((a, b) => b.value - a.value)

  const spaceRight = window.innerWidth - x - OFFSET
  const left = spaceRight >= TOOLTIP_W ? x + OFFSET : x - TOOLTIP_W - OFFSET

  return createPortal(
    <div
      style={{
        position: 'fixed',
        top: y - 8,
        left,
        width: TOOLTIP_W,
        zIndex: 9999,
        pointerEvents: 'none',
      }}
      className="bg-white border border-slate-200 rounded-xl shadow-xl p-3 text-xs"
    >
      <p className="font-semibold text-slate-700 mb-2">Week of {fmtWeekFull(week)}</p>
      {activeEntries.map((p, i) => {
        const meta = products.find(pr => pr.label === p.dataKey)
        const gmv  = p.payload?.[`${p.dataKey}_gmv`] ?? 0
        return (
          <div key={i} className="flex items-start gap-2 mb-1.5 last:mb-0">
            <span
              className="mt-0.5 shrink-0 inline-block w-2.5 h-2.5 rounded-sm"
              style={{ background: p.fill }}
            />
            <div>
              <span className="text-slate-700 font-medium">{meta?.product ?? p.dataKey}</span>
              <span className="text-slate-400 ml-1">· {meta?.vendor ?? ''}</span>
              <div className="text-slate-500">{p.value} bookings · {fmtEur(gmv)} GMV</div>
            </div>
          </div>
        )
      })}
    </div>,
    document.body
  )
}

export default function TopProductsChart({ dateRange = {}, filters = {} }) {
  const [products, setProducts] = useState([])
  const [weeks, setWeeks]       = useState([])
  const [loading, setLoading]   = useState(true)
  const [apiError, setApiError] = useState(null)
  const [tooltip, setTooltip]   = useState(null)

  const paramKey = JSON.stringify({ ...filters, ...dateRange })

  useEffect(() => {
    setLoading(true)
    setApiError(null)
    api.topProducts({ ...filters, ...dateRange })
      .then(res => {
        setProducts(res.data.products ?? [])
        setWeeks(res.data.weeks ?? [])
      })
      .catch(err => {
        setApiError(err?.response?.data?.detail || err?.message || String(err))
        setProducts([])
        setWeeks([])
      })
      .finally(() => setLoading(false))
  }, [paramKey])

  if (loading) {
    return (
      <div className="card p-4">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
          Top 10 Products — Weekly Bookings
        </p>
        <div className="h-48 flex items-center justify-center text-xs text-slate-400">Loading…</div>
      </div>
    )
  }

  if (!products.length || !weeks.length) {
    return (
      <div className="card p-4">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
          Top 10 Products — Weekly Bookings
        </p>
        {apiError
          ? <p className="text-xs text-red-500 text-center py-8 break-all">API error: {apiError}</p>
          : <p className="text-xs text-slate-400 text-center py-8">
              No product data for this period. Click Sync Data to populate.
            </p>
        }
      </div>
    )
  }

  const colourOf = {}
  products.forEach((p, i) => { colourOf[p.label] = COLOURS[i % COLOURS.length] })

  const YAXIS_W    = 40
  const naturalMinW = weeks.length * MIN_WEEK_PX + YAXIS_W

  function handleMouseMove(state, event) {
    if (!state?.isTooltipActive || !state.activePayload?.length) {
      setTooltip(null)
      return
    }
    setTooltip({
      x: event.clientX,
      y: event.clientY,
      week: state.activeLabel,
      entries: state.activePayload,
    })
  }

  return (
    <>
      <div className="card p-4">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">
          Top 10 Products — Weekly Bookings
        </p>
        <p className="text-[10px] text-slate-400 mb-3">
          Stacked bars · each colour = one product · hover for bookings &amp; GMV per week
          {weeks.length > 14 && ' · scroll horizontally to see all weeks'}
        </p>

        <div style={{ overflowX: 'auto', overflowY: 'hidden' }}>
          <div style={{ minWidth: naturalMinW }}>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart
                data={weeks}
                margin={{ top: 4, right: 16, left: 0, bottom: 0 }}
                onMouseMove={handleMouseMove}
                onMouseLeave={() => setTooltip(null)}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis
                  dataKey="week"
                  tickFormatter={fmtWeek}
                  tick={{ fontSize: 10, fill: '#94a3b8' }}
                  axisLine={false} tickLine={false}
                  interval={weeks.length > 20 ? Math.ceil(weeks.length / 15) - 1 : 0}
                />
                <YAxis
                  allowDecimals={false}
                  tick={{ fontSize: 10, fill: '#94a3b8' }}
                  axisLine={false} tickLine={false}
                  width={YAXIS_W}
                />
                {/* Built-in tooltip disabled — we use the portal version instead */}
                <Tooltip content={() => null} cursor={{ fill: '#f8fafc' }} />
                <Legend
                  wrapperStyle={{ fontSize: 10, paddingTop: 10 }}
                  formatter={v => {
                    const meta = products.find(p => p.label === v)
                    return truncate(meta ? `${meta.product} · ${meta.vendor}` : v, 36)
                  }}
                />
                {products.map((p, i) => (
                  <Bar
                    key={p.label}
                    dataKey={p.label}
                    stackId="products"
                    fill={colourOf[p.label]}
                    radius={i === products.length - 1 ? [3, 3, 0, 0] : [0, 0, 0, 0]}
                    maxBarSize={48}
                    isAnimationActive={false}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <p className="text-[10px] text-slate-400 mt-1.5">
          Each week = Monday start · excludes Cancelled bookings · segments ordered by total period volume
        </p>
      </div>

      <PortalTooltip data={tooltip} products={products} />
    </>
  )
}
