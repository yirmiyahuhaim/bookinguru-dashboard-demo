import { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ComposedChart, Line, Legend,
} from 'recharts'
import { api } from '../api/client'

const fmtEur = v => `€${Number(v).toLocaleString('en-EU', { maximumFractionDigits: 0 })}`
const truncate = (str, n) => str && str.length > n ? str.slice(0, n - 1) + '…' : str

const fmtWeek = str => {
  const d = new Date(str + 'T00:00:00')
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

const fmtWeekFull = str => {
  const d = new Date(str + 'T00:00:00')
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

const VENDOR_COLOURS = [
  '#3b82f6','#10b981','#f59e0b','#8b5cf6','#ec4899',
  '#06b6d4','#84cc16','#f97316','#6366f1','#14b8a6',
]

const TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'weekly',   label: 'Weekly Performance' },
]

export default function TopVendorsChart({ dateRange = {}, filters = {} }) {
  const [vendors, setVendors]         = useState([])
  const [loading, setLoading]         = useState(true)
  const [apiError, setApiError]       = useState(null)
  const [selected, setSelected]       = useState(null)
  const [modalTab, setModalTab]       = useState('overview')

  // Overview tab data
  const [products, setProducts]           = useState([])
  const [prodLoading, setProdLoading]     = useState(false)
  const [hotels, setHotels]               = useState([])
  const [hotelsLoading, setHotelsLoading] = useState(false)

  // Weekly tab data
  const [weeklyData, setWeeklyData]       = useState([])
  const [weeklyLoading, setWeeklyLoading] = useState(false)
  const [weeklyFetched, setWeeklyFetched] = useState(false)  // lazy — only fetch once per vendor

  const paramKey = JSON.stringify(filters)

  useEffect(() => {
    setLoading(true)
    setSelected(null)
    setApiError(null)
    api.topVendors({ ...filters })
      .then(res => setVendors(res.data))
      .catch(err => {
        const msg = err?.response?.data?.detail || err?.message || String(err)
        setApiError(msg)
        setVendors([])
      })
      .finally(() => setLoading(false))
  }, [paramKey])

  function handleVendorClick(entry) {
    if (!entry) return
    const name = entry.vendor
    setSelected(name)
    setModalTab('overview')
    setWeeklyFetched(false)
    setWeeklyData([])

    // Fetch overview data immediately
    setProdLoading(true)
    setHotelsLoading(true)
    api.vendorProducts(name, { ...dateRange })
      .then(res => setProducts(res.data))
      .catch(() => setProducts([]))
      .finally(() => setProdLoading(false))
    api.vendorHotels(name, { ...dateRange })
      .then(res => setHotels(res.data))
      .catch(() => setHotels([]))
      .finally(() => setHotelsLoading(false))
  }

  function handleTabSwitch(tab) {
    setModalTab(tab)
    if (tab === 'weekly' && !weeklyFetched && selected) {
      setWeeklyLoading(true)
      api.vendorWeeklyPerformance(selected, { ...dateRange })
        .then(res => setWeeklyData(res.data))
        .catch(() => setWeeklyData([]))
        .finally(() => { setWeeklyLoading(false); setWeeklyFetched(true) })
    }
  }

  if (loading) {
    return (
      <div className="card p-4">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Top 10 Vendors — by Bookings</p>
        <div className="h-48 flex items-center justify-center text-xs text-slate-400">Loading…</div>
      </div>
    )
  }

  if (!vendors.length) {
    return (
      <div className="card p-4">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Top 10 Vendors — by Bookings</p>
        {apiError
          ? <p className="text-xs text-red-500 text-center py-8 break-all">API error: {apiError}</p>
          : <p className="text-xs text-slate-400 text-center py-8">
              No vendor data for this period. Click Sync Data to populate.
            </p>
        }
      </div>
    )
  }

  const chartData   = vendors.map((v, i) => ({ ...v, fill: VENDOR_COLOURS[i % VENDOR_COLOURS.length] }))
  const chartHeight = Math.max(180, vendors.length * 34 + 40)

  return (
    <>
      <div className="card p-4">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">
          Top 10 Vendors — by Bookings
        </p>
        <p className="text-[10px] text-slate-400 mb-3">Click a bar to drill into a vendor</p>
        <ResponsiveContainer width="100%" height={chartHeight}>
          <BarChart
            data={chartData}
            layout="vertical"
            margin={{ top: 4, right: 60, left: 0, bottom: 0 }}
            onClick={e => e?.activePayload && handleVendorClick(e.activePayload[0]?.payload)}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
            <XAxis type="number" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis
              type="category" dataKey="vendor"
              tickFormatter={s => truncate(s, 24)}
              tick={{ fontSize: 10, cursor: 'pointer' }}
              width={150} axisLine={false} tickLine={false}
            />
            <Tooltip
              formatter={(v, name) => name === 'bookings' ? [v, 'Bookings'] : [fmtEur(v), 'GMV']}
              labelFormatter={v => v}
              cursor={{ fill: '#f1f5f9' }}
            />
            <Bar dataKey="bookings" radius={[0, 3, 3, 0]} maxBarSize={22} style={{ cursor: 'pointer' }}>
              {chartData.map((entry, i) => (
                <Cell key={i} fill={entry.fill} opacity={selected && selected !== entry.vendor ? 0.4 : 1} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <p className="text-[10px] text-slate-400 mt-1">
          Source: BookinGuru provider company · excludes Cancelled bookings
        </p>
      </div>

      {/* Vendor drill-down modal */}
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
            {/* Header */}
            <div className="flex items-start justify-between px-5 py-4 border-b border-slate-100 shrink-0">
              <div>
                <h3 className="font-bold text-slate-800 text-base truncate max-w-xs">{selected}</h3>
                <p className="text-xs text-slate-400 mt-0.5">Vendor breakdown</p>
              </div>
              <button
                onClick={() => setSelected(null)}
                className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
              >
                <X size={15} />
              </button>
            </div>

            {/* Tab switcher */}
            <div className="px-5 pt-3 pb-2 flex gap-2 shrink-0">
              {TABS.map(t => (
                <button
                  key={t.key}
                  onClick={() => handleTabSwitch(t.key)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    modalTab === t.key
                      ? 'bg-blue-600 text-white shadow-sm'
                      : 'bg-white border border-slate-200 text-slate-600 hover:border-blue-300 hover:text-blue-600'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {/* ── Overview tab ─────────────────────────────────────────── */}
            {modalTab === 'overview' && (
              <div className="flex-1 overflow-y-auto">
                {/* Product chart */}
                <div className="px-4 py-4">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
                    Top Products
                  </p>
                  {prodLoading ? (
                    <div className="h-36 flex items-center justify-center text-xs text-slate-400">Loading…</div>
                  ) : !products.length ? (
                    <p className="text-xs text-slate-400 text-center py-6">No product data for this vendor.</p>
                  ) : (
                    <ResponsiveContainer width="100%" height={Math.max(120, products.length * 36 + 40)}>
                      <BarChart data={products} layout="vertical" margin={{ top: 4, right: 48, left: 0, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
                        <XAxis type="number" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <YAxis
                          type="category" dataKey="product"
                          tickFormatter={s => truncate(s, 28)}
                          tick={{ fontSize: 10 }} width={170}
                          axisLine={false} tickLine={false}
                        />
                        <Tooltip formatter={(v, name) => name === 'bookings' ? [v, 'Bookings'] : [fmtEur(v), 'GMV']} />
                        <Bar dataKey="bookings" fill="#6366f1" radius={[0, 3, 3, 0]} maxBarSize={22} />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </div>

                {/* Top hotels */}
                <div className="px-5 pb-4 border-t border-slate-100 pt-4">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
                    Top Hotels using this vendor
                  </p>
                  {hotelsLoading ? (
                    <p className="text-xs text-slate-400">Loading…</p>
                  ) : !hotels.length ? (
                    <p className="text-xs text-slate-400">No hotel data for this vendor.</p>
                  ) : (
                    <div className="space-y-2">
                      {hotels.map((h, i) => {
                        const maxB = hotels[0]?.bookings || 1
                        return (
                          <div key={h.hotel}>
                            <div className="flex items-center justify-between mb-0.5">
                              <span className="text-xs text-slate-700 truncate max-w-[60%]">
                                {i + 1}. {h.hotel}
                              </span>
                              <span className="text-xs text-slate-500 shrink-0 ml-2">
                                {h.bookings} bookings · GMV {fmtEur(h.gmv)}
                              </span>
                            </div>
                            <div className="h-1 bg-slate-100 rounded-full overflow-hidden">
                              <div
                                className="h-full rounded-full bg-indigo-400"
                                style={{ width: `${(h.bookings / maxB) * 100}%` }}
                              />
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>

                <div className="px-5 pb-4 pt-1">
                  <p className="text-[10px] text-slate-400">
                    Source: BookinGuru product &amp; provider company · Click outside to close
                  </p>
                </div>
              </div>
            )}

            {/* ── Weekly Performance tab ────────────────────────────────── */}
            {modalTab === 'weekly' && (
              <div className="flex-1 overflow-y-auto px-4 py-4">
                {weeklyLoading ? (
                  <div className="h-52 flex items-center justify-center text-xs text-slate-400">Loading…</div>
                ) : !weeklyData.length ? (
                  <p className="text-xs text-slate-400 text-center py-10">
                    No weekly data for this vendor in the selected period.
                  </p>
                ) : (
                  <>
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
                      Bookings per week
                    </p>
                    <ResponsiveContainer width="100%" height={240}>
                      <ComposedChart data={weeklyData} margin={{ top: 4, right: 44, left: 0, bottom: 0 }}>
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
                        <Tooltip
                          formatter={(v, name) =>
                            name === 'bookings' ? [v, 'Bookings'] : [fmtEur(v), 'GMV']
                          }
                          labelFormatter={fmtWeekFull}
                        />
                        <Legend
                          wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
                          formatter={v => v === 'bookings' ? 'Bookings' : 'GMV'}
                        />
                        <Bar
                          yAxisId="left"
                          dataKey="bookings"
                          fill="#3b82f6"
                          radius={[3, 3, 0, 0]}
                          maxBarSize={32}
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
                      </ComposedChart>
                    </ResponsiveContainer>

                    {/* Weekly table */}
                    <div className="mt-4 border border-slate-100 rounded-xl overflow-hidden">
                      <table className="w-full text-xs">
                        <thead className="bg-slate-50">
                          <tr className="text-slate-500 uppercase tracking-wide text-[10px]">
                            <th className="px-3 py-2 text-left">Week</th>
                            <th className="px-3 py-2 text-right">Bookings</th>
                            <th className="px-3 py-2 text-right">GMV</th>
                          </tr>
                        </thead>
                        <tbody>
                          {[...weeklyData].reverse().map((row, i) => (
                            <tr key={i} className="border-t border-slate-50 hover:bg-slate-50">
                              <td className="px-3 py-1.5 text-slate-600">{fmtWeekFull(row.week)}</td>
                              <td className="px-3 py-1.5 text-right font-medium text-slate-800">{row.bookings}</td>
                              <td className="px-3 py-1.5 text-right text-indigo-600">{fmtEur(row.gmv)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    <p className="text-[10px] text-slate-400 mt-3">
                      Bookings per week (blue bars) · GMV trend (purple line) · excludes Cancelled · Click outside to close
                    </p>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  )
}
