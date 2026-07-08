import { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer,
} from 'recharts'
import { api } from '../api/client'

const fmtEur = v => `€${Number(v).toLocaleString('en-EU', { maximumFractionDigits: 0 })}`

const fmtWeek = str => {
  const d = new Date(str + 'T00:00:00')
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

const fmtWeekFull = str => {
  const d = new Date(str + 'T00:00:00')
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

function WeeklyTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const bookings     = payload.find(p => p.dataKey === 'bookings')
  const prevBookings  = payload.find(p => p.dataKey === 'prev_bookings')
  const gmv           = payload.find(p => p.dataKey === 'gmv')
  const prevGmv       = payload.find(p => p.dataKey === 'prev_gmv')
  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-lg px-3 py-2.5 text-xs">
      <p className="font-semibold text-slate-700 mb-1">{fmtWeekFull(label)}</p>
      {bookings && <p style={{ color: '#3b82f6' }}>Bookings: <strong>{bookings.value}</strong></p>}
      {prevBookings && prevBookings.value != null && (
        <p style={{ color: '#94a3b8' }}>Bookings (last year): <strong>{prevBookings.value}</strong></p>
      )}
      {gmv && <p style={{ color: '#6366f1' }}>GMV: <strong>{fmtEur(gmv.value)}</strong></p>}
      {prevGmv && prevGmv.value != null && (
        <p style={{ color: '#f97316' }}>GMV (last year): <strong>{fmtEur(prevGmv.value)}</strong></p>
      )}
    </div>
  )
}

export default function VendorPortfolioWidget({ hotelId, dateRange = {} }) {
  const [vendors, setVendors]   = useState(null)
  const [selected, setSelected] = useState(null)
  const [weekly, setWeekly]     = useState(null)

  const key = JSON.stringify({ hotelId, dateRange })

  useEffect(() => {
    setVendors(null)
    setSelected(null)
    api.hotelTopVendors(hotelId, 500, dateRange)
      .then(r => setVendors(r.data))
      .catch(() => setVendors([]))
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleSelect(vendor) {
    setSelected(vendor)
    setWeekly(null)
    api.vendorWeeklyPerformance(vendor, { hotel_id: hotelId, ...dateRange })
      .then(r => setWeekly(r.data))
      .catch(() => setWeekly([]))
  }

  if (vendors === null) return null
  if (!vendors.length) return (
    <div className="card p-4">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">
        Vendor Portfolio for Given Hotel
      </p>
      <p className="text-xs text-slate-400 mt-2">No vendor data for this period (2026 bookings only — Column Q).</p>
    </div>
  )

  const max = vendors[0]?.bookings || 1

  return (
    <>
      <div className="card p-4">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">
          Vendor Portfolio for Given Hotel
        </p>
        <p className="text-[10px] text-slate-400 mb-3">
          All {vendors.length} vendors active at this hotel · ranked by bookings · click a vendor for weekly detail
        </p>
        <div className="space-y-2.5 max-h-96 overflow-y-auto pr-1">
          {vendors.map((v, i) => (
            <button
              key={v.vendor}
              onClick={() => handleSelect(v.vendor)}
              className="w-full text-left group"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-slate-700 group-hover:text-blue-600 truncate max-w-[60%]">
                  {i + 1}. {v.vendor}
                </span>
                <span className="text-[11px] text-slate-500 shrink-0 ml-2">
                  {v.bookings} bookings · <span className="text-slate-400">GMV</span> {fmtEur(v.gmv)}
                </span>
              </div>
              <div className="h-1 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full bg-blue-400 group-hover:bg-blue-500 transition-colors"
                  style={{ width: `${(v.bookings / max) * 100}%` }}
                />
              </div>
            </button>
          ))}
        </div>
        <p className="text-[10px] text-slate-400 mt-3">
          Excludes Cancelled
        </p>
      </div>

      {/* Vendor weekly drill-down modal, with last-season comparison */}
      {selected && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
          onClick={() => setSelected(null)}
        >
          <div
            className="bg-white rounded-2xl shadow-2xl w-full max-w-lg flex flex-col"
            style={{ maxHeight: '88vh' }}
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-start justify-between px-5 py-4 border-b border-slate-100 shrink-0">
              <div>
                <h3 className="font-bold text-slate-800 text-base truncate max-w-xs">{selected}</h3>
                <p className="text-xs text-slate-400 mt-0.5">Weekly performance at this hotel · vs same week last season</p>
              </div>
              <button
                onClick={() => setSelected(null)}
                className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
              >
                <X size={15} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-4 py-4">
              {weekly === null ? (
                <div className="h-52 flex items-center justify-center text-xs text-slate-400">Loading…</div>
              ) : !weekly.length ? (
                <p className="text-xs text-slate-400 text-center py-10">
                  No weekly data for this vendor at this hotel in the selected period.
                </p>
              ) : (
                <>
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
                    Bookings &amp; GMV per week
                  </p>
                  <ResponsiveContainer width="100%" height={260}>
                    <ComposedChart data={weekly} margin={{ top: 4, right: 44, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                      <XAxis
                        dataKey="week"
                        tickFormatter={fmtWeek}
                        tick={{ fontSize: 10, fill: '#94a3b8' }}
                        axisLine={false} tickLine={false}
                        interval="preserveStartEnd"
                      />
                      <YAxis
                        yAxisId="left"
                        allowDecimals={false}
                        tick={{ fontSize: 10, fill: '#94a3b8' }}
                        axisLine={false} tickLine={false}
                        width={32}
                      />
                      <YAxis
                        yAxisId="right"
                        orientation="right"
                        tickFormatter={n => `€${n >= 1000 ? `${(n/1000).toFixed(0)}k` : n}`}
                        tick={{ fontSize: 10, fill: '#6366f1' }}
                        axisLine={false} tickLine={false}
                        width={44}
                      />
                      <Tooltip content={<WeeklyTooltip />} />
                      <Legend
                        wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
                        formatter={v => {
                          if (v === 'bookings')      return 'Bookings'
                          if (v === 'prev_bookings')  return 'Bookings (Last Year)'
                          if (v === 'gmv')            return 'GMV'
                          if (v === 'prev_gmv')       return 'GMV (Last Year)'
                          return v
                        }}
                      />
                      <Bar
                        yAxisId="left"
                        dataKey="bookings"
                        fill="#3b82f6"
                        radius={[3, 3, 0, 0]}
                        maxBarSize={22}
                      />
                      <Bar
                        yAxisId="left"
                        dataKey="prev_bookings"
                        fill="#94a3b8"
                        radius={[3, 3, 0, 0]}
                        maxBarSize={22}
                      />
                      <Line
                        yAxisId="right"
                        dataKey="gmv"
                        stroke="#6366f1"
                        strokeWidth={2}
                        dot={{ r: 3, fill: '#6366f1', strokeWidth: 0 }}
                        activeDot={{ r: 5 }}
                        connectNulls
                      />
                      <Line
                        yAxisId="right"
                        dataKey="prev_gmv"
                        stroke="#f97316"
                        strokeWidth={2}
                        strokeDasharray="5 4"
                        dot={{ r: 2.5, fill: '#f97316', strokeWidth: 0 }}
                        activeDot={{ r: 4 }}
                        connectNulls
                      />
                    </ComposedChart>
                  </ResponsiveContainer>

                  <div className="mt-4 border border-slate-100 rounded-xl overflow-hidden">
                    <table className="w-full text-xs">
                      <thead className="bg-slate-50">
                        <tr className="text-slate-500 uppercase tracking-wide text-[10px]">
                          <th className="px-3 py-2 text-left">Week</th>
                          <th className="px-3 py-2 text-right">Bookings</th>
                          <th className="px-3 py-2 text-right">Last Yr</th>
                          <th className="px-3 py-2 text-right">GMV</th>
                          <th className="px-3 py-2 text-right">Last Yr</th>
                        </tr>
                      </thead>
                      <tbody>
                        {[...weekly].reverse().map((row, i) => (
                          <tr key={i} className="border-t border-slate-50 hover:bg-slate-50">
                            <td className="px-3 py-1.5 text-slate-600">{fmtWeekFull(row.week)}</td>
                            <td className="px-3 py-1.5 text-right font-medium text-slate-800">{row.bookings}</td>
                            <td className="px-3 py-1.5 text-right text-slate-400">{row.prev_bookings ?? '—'}</td>
                            <td className="px-3 py-1.5 text-right text-indigo-600">{fmtEur(row.gmv)}</td>
                            <td className="px-3 py-1.5 text-right text-slate-400">{row.prev_gmv != null ? fmtEur(row.prev_gmv) : '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <p className="text-[10px] text-slate-400 mt-3">
                    Bookings (blue bars) &amp; GMV (indigo line) for the selected period · grey dashed = same week last season (364 days back) · excludes Cancelled · Click outside to close
                  </p>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
