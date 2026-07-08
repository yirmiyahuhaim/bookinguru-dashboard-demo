import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, Table2 } from 'lucide-react'
import { api } from '../api/client'

// "2026-06-15" -> "Jun 15 – Jun 21"
const fmtWeekRange = iso => {
  if (!iso) return ''
  const start = new Date(iso + 'T00:00:00')
  const end = new Date(start); end.setDate(end.getDate() + 6)
  const f = d => d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
  return `${f(start)} – ${f(end)}`
}
const fmtWeekShort = iso => {
  if (!iso) return ''
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

// Light green heatmap — intensity scales with the cell value vs the matrix max.
function cellStyle(v, max) {
  if (!v) return { background: 'transparent', color: '#cbd5e1' }       // zero = muted
  const t = max > 0 ? Math.min(v / max, 1) : 0
  // interpolate alpha 0.08 → 0.55 of emerald
  const alpha = 0.08 + t * 0.47
  return {
    background: `rgba(16, 185, 129, ${alpha.toFixed(2)})`,
    color: t > 0.6 ? '#065f46' : '#334155',
    fontWeight: t > 0.45 ? 600 : 400,
  }
}

export default function HotelWeeklyMatrix({ filters = {}, dateRange = {} }) {
  const navigate = useNavigate()
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)
  const [collapsed, setCollapsed] = useState(true)   // minimized by default

  const paramKey = JSON.stringify({ ...filters, ...dateRange })

  useEffect(() => {
    let alive = true
    setLoading(true); setError(null)
    api.hotelWeeklyMatrix({ ...filters, ...dateRange })
      .then(res => { if (alive) setData(res.data) })
      .catch(err => { if (alive) setError(err?.response?.data?.detail || err?.message || String(err)) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [paramKey])

  const weeks = data?.weeks || []
  // Hide hotels with zero bookings across every week in the selected period —
  // they add rows without adding signal to this view.
  const rows  = (data?.rows || []).filter(r => r.total > 0)
  const maxCell = rows.reduce((m, r) => Math.max(m, ...r.weeks), 0)

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/60 shadow-sm overflow-hidden">
      {/* Header is inlined (not a nested component) so the button is never
          remounted on re-render — a remount mid-click would swallow the click. */}
      <button
        type="button"
        onClick={() => setCollapsed(c => !c)}
        className="w-full px-5 py-3.5 bg-gradient-to-r from-emerald-50/60 to-white border-b border-slate-100 flex items-center justify-between text-left hover:from-emerald-50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <ChevronDown size={15} className={`text-slate-400 transition-transform ${collapsed ? '-rotate-90' : ''}`} />
          <Table2 size={14} className="text-emerald-500" />
          <h2 className="text-[11px] font-bold text-slate-500 uppercase tracking-widest">Hotel Weekly Bookings</h2>
          {collapsed && rows.length > 0 && (
            <span className="ml-1 text-[10px] font-semibold text-emerald-600 bg-emerald-100 rounded-full px-2 py-0.5 normal-case tracking-normal">
              {rows.length} hotels · {weeks.length} weeks
            </span>
          )}
        </div>
        <span className="text-[10px] text-slate-300 normal-case tracking-normal">
          {collapsed ? 'Click to expand' : 'Ranked by total bookings'}
        </span>
      </button>
      {!collapsed && (
        <div className="p-5">
          {loading ? (
            <div className="text-xs text-slate-400 py-4">Loading weekly bookings…</div>
          ) : error ? (
            <div className="text-xs text-red-500 py-4 break-all">Could not load: {error}</div>
          ) : !rows.length ? (
            <div className="text-xs text-slate-400 py-4">No weekly booking data for this period.</div>
          ) : (
            <>
              <div className="overflow-x-auto border border-slate-100 rounded-xl">
                <table className="text-xs border-collapse min-w-full">
                  <thead>
                    <tr className="bg-slate-50">
                      <th className="sticky left-0 z-20 bg-slate-50 py-2 text-center font-semibold text-slate-500 uppercase tracking-wide text-[10px] border-b border-slate-100 w-[42px] min-w-[42px]">
                        #
                      </th>
                      <th className="sticky left-[42px] z-10 bg-slate-50 px-3 py-2 text-left font-semibold text-slate-500 uppercase tracking-wide text-[10px] border-b border-r border-slate-100 min-w-[180px]">
                        Hotel
                      </th>
                      {weeks.map((w, i) => (
                        <th key={i} title={fmtWeekRange(w)}
                            className="px-2.5 py-2 text-center font-medium text-slate-400 text-[10px] border-b border-slate-100 whitespace-nowrap">
                          {fmtWeekShort(w)}
                        </th>
                      ))}
                      <th className="sticky right-0 z-10 bg-slate-50 px-3 py-2 text-center font-semibold text-slate-600 uppercase tracking-wide text-[10px] border-b border-l border-slate-100">
                        Total
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r, ri) => (
                      <tr
                        key={ri}
                        onClick={() => r.hotel_id && navigate(`/hotels/${r.hotel_id}`)}
                        className={`group ${r.hotel_id ? 'cursor-pointer' : ''}`}
                        title={r.hotel_id ? `Open ${r.hotel} details` : undefined}
                      >
                        <td className="sticky left-0 z-20 bg-white group-hover:bg-slate-50 py-1.5 text-center font-semibold text-slate-400 tabular-nums w-[42px] min-w-[42px]">
                          {ri + 1}
                        </td>
                        <td className="sticky left-[42px] z-10 bg-white group-hover:bg-slate-50 px-3 py-1.5 text-slate-700 group-hover:text-blue-600 font-medium border-r border-slate-100 whitespace-nowrap max-w-[220px] truncate"
                            title={r.hotel}>
                          {r.hotel}
                        </td>
                        {r.weeks.map((v, ci) => (
                          <td key={ci} className="px-2.5 py-1.5 text-center tabular-nums" style={cellStyle(v, maxCell)}>
                            {v || ''}
                          </td>
                        ))}
                        <td className="sticky right-0 z-10 bg-white group-hover:bg-slate-50 px-3 py-1.5 text-center font-bold text-slate-800 border-l border-slate-100 tabular-nums">
                          {r.total}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-[10px] text-slate-400 mt-2">
                Weekly paid bookings per active hotel · ranked by total in the selected period · darker green = higher volume ·
                week label = Monday start (hover a column for the full range) · click a hotel row to open its details.
              </p>
            </>
          )}
        </div>
      )}
    </section>
  )
}
