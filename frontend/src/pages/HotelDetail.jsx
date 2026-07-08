import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useFilters } from '../context/FilterContext'
import Navbar from '../components/Navbar'
import KPICard from '../components/KPICard'
import DateRangePicker from '../components/DateRangePicker'
import VendorWeeklyChart from '../components/VendorWeeklyChart'
import VendorPortfolioWidget from '../components/VendorPortfolioWidget'
import { GMVChart, NetRevenueChart, TransactionsChart, AttachRateChart } from '../components/Charts'
import { ArrowLeft, MapPin } from 'lucide-react'

const fmt = n => n == null ? '—' : `€${Number(n).toLocaleString('en-EU', { maximumFractionDigits: 0 })}`
const pct = n => n == null ? '—' : `${Number(n).toFixed(1)}%`
const fmtSmall = n => n == null ? '—' : `€${Number(n).toFixed(2)}`

const MEDAL = ['🥇', '🥈', '🥉']

function TopVendorsWidget({ hotelId, dateRange }) {
  const [vendors, setVendors] = useState(null)
  const key = JSON.stringify({ hotelId, dateRange })

  useEffect(() => {
    setVendors(null)
    api.hotelTopVendors(hotelId, 3, dateRange)
      .then(r => setVendors(r.data))
      .catch(() => setVendors([]))
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps

  if (vendors === null) return null
  if (!vendors.length) return (
    <div className="card p-5">
      <h2 className="text-sm font-semibold text-slate-700 mb-2">Top Vendors</h2>
      <p className="text-xs text-slate-400">No vendor data for this period (2026 bookings only — Column Q).</p>
    </div>
  )

  const max = vendors[0]?.bookings || 1

  return (
    <div className="card p-5">
      <h2 className="text-sm font-semibold text-slate-700 mb-4">Top Vendors</h2>
      <div className="space-y-3">
        {vendors.map((v, i) => (
          <div key={v.vendor}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm text-slate-700 truncate max-w-[60%]">
                {MEDAL[i]} {v.vendor}
              </span>
              <span className="text-xs text-slate-500 shrink-0 ml-2">
                {v.bookings} bookings · <span className="text-slate-400">GMV</span> {fmt(v.gmv)}
              </span>
            </div>
            <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${(v.bookings / max) * 100}%`,
                  backgroundColor: i === 0 ? '#3b82f6' : i === 1 ? '#10b981' : '#f59e0b',
                }}
              />
            </div>
          </div>
        ))}
      </div>
      <p className="text-[10px] text-slate-400 mt-4">Excludes Cancelled</p>
    </div>
  )
}

function fmtPeriod(dateRange) {
  if (!dateRange?.date_from && !dateRange?.date_to) return 'All time'
  if (dateRange?.date_from && dateRange?.date_to)
    return `${dateRange.date_from} → ${dateRange.date_to}`
  return ''
}

export default function HotelDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { dateRange, setDateRange } = useFilters()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true)
    setError('')
    const params = {}
    if (dateRange?.date_from) params.date_from = dateRange.date_from
    if (dateRange?.date_to)   params.date_to   = dateRange.date_to
    api.hotel(id, params)
      .then(r => setData(r.data))
      .catch(() => setError('Failed to load hotel data.'))
      .finally(() => setLoading(false))
  }, [id, dateRange])

  if (loading) return (
    <div className="min-h-screen bg-slate-50">
      <Navbar />
      <div className="max-w-5xl mx-auto px-4 py-12 text-center text-slate-400">Loading…</div>
    </div>
  )

  if (error || !data) return (
    <div className="min-h-screen bg-slate-50">
      <Navbar />
      <div className="max-w-5xl mx-auto px-4 py-12 text-center text-red-500">{error || 'Hotel not found.'}</div>
    </div>
  )

  const { hotel, kpis, trend } = data
  const badgeClass = {
    Active:   'badge-active',
    Pipeline: 'badge-pipeline',
    Churned:  'badge-churned',
  }[hotel.pipeline_status] || 'badge'

  return (
    <div className="min-h-screen bg-slate-50">
      <Navbar />

      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">

        {/* Back + Header */}
        <div>
          <button onClick={() => navigate(-1)} className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-900 transition-colors mb-3">
            <ArrowLeft size={14} /> Back to Portfolio
          </button>
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h1 className="text-xl font-bold text-slate-900 truncate">{hotel.name}</h1>
              <div className="flex items-center gap-1.5 text-sm text-slate-500 mt-1">
                <MapPin size={13} />
                {hotel.market} · {hotel.property_type} · {hotel.room_count} rooms · {hotel.seasonality}
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {kpis.activity_class && (
                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold
                  ${kpis.activity_class === 'A' ? 'bg-blue-100 text-blue-700' :
                    kpis.activity_class === 'B' ? 'bg-emerald-100 text-emerald-700' :
                                                  'bg-amber-100 text-amber-700'}`}>
                  Class {kpis.activity_class}
                </span>
              )}
              <span className={badgeClass}>{hotel.pipeline_status}</span>
            </div>
          </div>
        </div>

        {/* Date range selector */}
        <div className="card px-4 py-3">
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <div className="shrink-0">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Time Range</p>
              <p className="text-xs text-slate-400 mt-0.5">{fmtPeriod(dateRange)}</p>
            </div>
            <div className="sm:border-l sm:border-slate-100 sm:pl-3">
              <DateRangePicker value={dateRange} onChange={setDateRange} />
            </div>
          </div>
        </div>

        {/* KPI strip */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
          <KPICard label="Total GMV"     value={fmt(kpis.total_gmv)}        colour="blue" />
          <KPICard label="Net Revenue"   value={fmt(kpis.net_revenue)}      colour="green" />
          <KPICard label="ARPAR_BG"      value={fmtSmall(kpis.arpar_bg)}   colour="blue"
                   sub="Net Rev / Rooms" />
          <KPICard label="Attach Rate"   value={pct(kpis.attach_rate)}     colour={kpis.attach_rate >= 15 ? 'green' : kpis.attach_rate >= 5 ? 'amber' : 'red'}
                   sub={kpis.attach_rate < 5 ? 'Below target (<5%)' : kpis.attach_rate >= 15 ? 'Strong (≥15%)' : 'Moderate'} />
          <KPICard label="Avg Take Rate" value={pct(kpis.avg_take_rate)}   colour="slate" />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <KPICard label="Total Bookings" value={kpis.total_transactions?.toLocaleString()} colour="slate" />
          <KPICard label="SaaS MRR"       value={fmt(kpis.saas_mrr)} colour="green" />
        </div>

        <TopVendorsWidget hotelId={id} dateRange={dateRange} />

        <VendorWeeklyChart hotelId={id} dateRange={dateRange} />

        <VendorPortfolioWidget hotelId={id} dateRange={dateRange} />

        {/* Charts */}
        {trend.length > 0 ? (
          <>
            <GMVChart        data={trend} />
            <NetRevenueChart data={trend} />

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <TransactionsChart data={trend} />
              <AttachRateChart   data={trend} />
            </div>
          </>
        ) : (
          <div className="card p-10 text-center text-slate-400">
            <p className="text-3xl mb-2">📊</p>
            <p>No performance data for this period.</p>
          </div>
        )}

        {/* Raw trend table */}
        {trend.length > 0 && (
          <div className="card overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-100">
              <h2 className="text-sm font-semibold text-slate-700">Weekly Performance Data</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
                    <th className="px-4 py-3 text-left">Week</th>
                    <th className="px-4 py-3 text-right">GMV</th>
                    <th className="px-4 py-3 text-right">Bookings</th>
                    <th className="px-4 py-3 text-right">Net Rev</th>
                    <th className="px-4 py-3 text-right">Take Rate</th>
                    <th className="px-4 py-3 text-right">Attach Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {[...trend].reverse().map((row, i) => (
                    <tr key={i} className="border-t border-slate-50 hover:bg-slate-50 transition-colors">
                      <td className="px-4 py-2.5 text-slate-600">{row.week_start_date}</td>
                      <td className="px-4 py-2.5 text-right font-medium">{fmt(row.gmv)}</td>
                      <td className="px-4 py-2.5 text-right">{row.transactions}</td>
                      <td className="px-4 py-2.5 text-right text-emerald-600 font-medium">{fmt(row.net_revenue)}</td>
                      <td className="px-4 py-2.5 text-right">{pct(row.take_rate)}</td>
                      <td className="px-4 py-2.5 text-right">{pct(row.attach_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
