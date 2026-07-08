import { useState, useEffect, useCallback, useRef } from 'react'
import { api, API_BASE } from '../api/client'
import { useFilters } from '../context/FilterContext'
import Navbar from '../components/Navbar'
import KPICard from '../components/KPICard'
import HotelCard from '../components/HotelCard'
import FilterBar from '../components/FilterBar'
import DateRangePicker from '../components/DateRangePicker'
import { GMVChart, NetRevenueChart, AOVChart, AttachRateChart, ActiveHotelsChart, TransactionsChart, HotelAOVChart } from '../components/Charts'
import { FileDown, FileText, FileSpreadsheet, RefreshCw, Wifi, WifiOff, ChevronDown, ChevronRight, Lock, Unlock, Search, X } from 'lucide-react'
import DrillDownModal from '../components/DrillDownModal'
import ForecastModal from '../components/ForecastModal'
import TopVendorsChart from '../components/TopVendorsChart'
import TopProductsChart from '../components/TopProductsChart'
import WeeklyInsights from '../components/WeeklyInsights'
import HotelWeeklyMatrix from '../components/HotelWeeklyMatrix'

const fmt  = n => n == null ? '—' : `€${Number(n).toLocaleString('en-EU', { maximumFractionDigits: 0 })}`
const fmt2 = n => n == null ? '—' : `€${Number(n).toLocaleString('en-EU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const pct  = n => n == null ? '—' : `${Number(n).toFixed(1)}%`
const mo   = n => n == null ? '—' : `${Number(n).toFixed(1)} mo`
const num  = n => n == null ? '—' : Number(n).toLocaleString()
const dec  = (n, d = 2) => n == null ? '—' : Number(n).toFixed(d)
const fmtK = n => n == null ? '—' : `€${(Number(n) / 1000).toFixed(0)}k`

// ── Collapsible tier wrapper ─────────────────────────────────────────────────
function Tier({ title, subtitle, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/60 backdrop-blur-sm shadow-sm overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-3 px-5 py-3.5 bg-gradient-to-r from-slate-50 to-white border-b border-slate-100 hover:from-slate-100/80 transition-colors"
      >
        {open
          ? <ChevronDown  size={14} className="text-slate-400 shrink-0" />
          : <ChevronRight size={14} className="text-slate-400 shrink-0" />}
        <span className="text-[11px] font-bold text-slate-500 uppercase tracking-widest">{title}</span>
        {subtitle && (
          <span className="text-xs text-slate-400 font-normal normal-case tracking-normal hidden sm:block">
            — {subtitle}
          </span>
        )}
      </button>
      {open && <div className="p-5 space-y-4">{children}</div>}
    </section>
  )
}

// ── Locked card for internal-only metrics ────────────────────────────────────
function LockedMetricCard({ label, icon, onUnlock }) {
  return (
    <button
      onClick={onUnlock}
      className="card p-3 sm:p-5 flex flex-col gap-1 border border-slate-200 bg-slate-50 text-left w-full hover:bg-slate-100 transition-colors group"
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-400 leading-tight">{label}</span>
        <span className="text-base sm:text-lg shrink-0 ml-1">{icon}</span>
      </div>
      <div className="flex items-center gap-1.5 mt-1">
        <Lock size={14} className="text-slate-400 group-hover:text-slate-600 transition-colors" />
        <span className="text-xs text-slate-400 group-hover:text-slate-600 transition-colors">Internal only · click to unlock</span>
      </div>
    </button>
  )
}

// ── Placeholder card for metrics needing external data ───────────────────────
function PlaceholderCard({ label, icon, source }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-3 flex items-center gap-3">
      <span className="text-lg shrink-0">{icon}</span>
      <div className="min-w-0">
        <p className="text-xs font-semibold text-slate-500 truncate">{label}</p>
        <p className="text-[10px] text-slate-400 mt-0.5">{source}</p>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [summary, setSummary]           = useState(null)
  const [hotels, setHotels]             = useState([])
  const [trendData, setTrendData]       = useState([])
  const [options, setOptions]           = useState({ markets: [], property_types: [], statuses: [] })
  const [filters, setFilters]           = useState({})
  const [hotelSearch, setHotelSearch]   = useState('')
  const { dateRange, setDateRange }     = useFilters()
  const [loading, setLoading]           = useState(true)
  const [error, setError]               = useState('')
  const [gaData, setGaData]             = useState(null)
  const [gaLoading, setGaLoading]       = useState(true)
  const [drillMetric, setDrillMetric]   = useState(null)   // 'active_hotels' | 'rooms_live' | 'net_revenue' | 'gmv' | 'attach_rate'
  const [forecastData, setForecastData] = useState(null)   // {bookings: [...], gmv: [...]}
  const [forecastMetric, setForecastMetric]   = useState(null)   // 'bookings' | 'gmv'
  // Internal metrics (Cash, Runway) — hidden behind a second password
  const [internalData, setInternalData]         = useState(null)
  const [showUnlockForm, setShowUnlockForm]     = useState(false)
  const [internalInput, setInternalInput]       = useState('')
  const [internalError, setInternalError]       = useState('')
  const [internalLoading, setInternalLoading]   = useState(false)
  const internalInputRef = useRef(null)

  const allFilters = { ...filters, ...dateRange }

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      try { await api.health() } catch (_) {}
      const [sumRes, hotelsRes, trendRes] = await Promise.all([
        api.summary(allFilters),
        api.hotels({ ...allFilters }),
        api.trend(allFilters),
      ])
      setSummary(sumRes.data)
      setHotels(hotelsRes.data)
      setTrendData(trendRes.data)
    } catch (e) {
      const msg = e?.response?.status
        ? `Error ${e.response.status}: ${JSON.stringify(e.response.data)}`
        : `Network error: ${e.message}`
      setError(msg)
    } finally {
      setLoading(false)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, dateRange])

  const loadGA = useCallback(async () => {
    setGaLoading(true)
    try {
      const res = await api.ga4(30)
      setGaData(res.data)
    } catch (_) {
      setGaData({ connected: false })
    } finally {
      setGaLoading(false)
    }
  }, [])

  const loadForecast = useCallback(async () => {
    try {
      const res = await api.forecast()
      setForecastData(res.data)
    } catch (_) {
      setForecastData({ bookings: [], gmv: [] })
    }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => { loadGA() }, [loadGA])
  useEffect(() => { loadForecast() }, [loadForecast])
  // Filter dropdown options are static metadata — fetch once, not on every filter change.
  useEffect(() => { api.filters().then(res => setOptions(res.data)).catch(() => {}) }, [])

  function handleFilterChange(f) { setFilters(f) }

  function exportParams() {
    return new URLSearchParams(
      Object.fromEntries(Object.entries({ ...filters, ...dateRange }).filter(([, v]) => v))
    ).toString()
  }

  function openPDF() {
    const params = exportParams()
    window.open(`${API_BASE}/reports/pdf${params ? '?' + params : ''}`, '_blank')
  }

  function downloadXLSX() {
    const params = exportParams()
    const a = document.createElement('a')
    a.href = `${API_BASE}/reports/xlsx${params ? '?' + params : ''}`
    a.download = 'bookinguru-report.xlsx'
    a.click()
  }

  async function downloadCSV() {
    const params = exportParams()
    const a = document.createElement('a')
    a.href = `${API_BASE}/reports/csv${params ? '?' + params : ''}`
    a.download = 'bookinguru-export.csv'
    a.click()
  }

  function openUnlockForm() {
    setInternalInput('')
    setInternalError('')
    setShowUnlockForm(true)
    setTimeout(() => internalInputRef.current?.focus(), 50)
  }

  async function submitInternalToken(e) {
    e.preventDefault()
    if (!internalInput.trim()) return
    setInternalLoading(true)
    setInternalError('')
    try {
      const res = await api.internalMetrics(internalInput.trim())
      setInternalData(res.data)
      sessionStorage.setItem('bg_internal', internalInput.trim())
      setShowUnlockForm(false)
    } catch (err) {
      const status = err.response?.status
      setInternalError(status === 401 ? 'Incorrect passcode.' : status === 503 ? 'Internal access not configured.' : 'Request failed.')
    } finally {
      setInternalLoading(false)
    }
  }

  // Restore internal session on mount
  useEffect(() => {
    const saved = sessionStorage.getItem('bg_internal')
    if (saved) {
      api.internalMetrics(saved)
        .then(res => setInternalData(res.data))
        .catch(() => sessionStorage.removeItem('bg_internal'))
    }
  }, [])

  const s = summary
  const runway = internalData?.runway_months
  const runwayColour   = runway == null ? 'slate' : runway < 9 ? 'red' : runway < 12 ? 'amber' : 'green'
  const attachColour   = v => v == null ? 'slate' : v >= 25 ? 'green' : v >= 15 ? 'blue' : v >= 5 ? 'amber' : 'red'
  const fmtPeriod = ({ date_from, date_to }) => {
    const fmt = d => new Date(d + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
    if (!date_from && !date_to) return 'All time'
    if (date_from && date_to)   return `${fmt(date_from)} → ${fmt(date_to)}`
    if (date_from)              return `From ${fmt(date_from)}`
    return `Until ${fmt(date_to)}`
  }
  const attachInterpret = v =>
    v < 5  ? 'very low — guests not yet engaging with extras'
    : v < 15 ? 'growing — product working but not yet viral'
    : v < 25 ? 'strong — most guests engaging with platform'
    :          'exceptional — case-study level adoption'
  const nrrColour      = v => v == null ? 'slate' : v >= 100 ? 'green' : v >= 90 ? 'amber' : 'red'
  const fillColour     = v => v == null ? 'slate' : v >= 90 ? 'green' : v >= 75 ? 'amber' : 'red'
  const varColour      = v => v == null ? 'slate' : v < 5 ? 'green' : v < 10 ? 'amber' : 'red'

  return (
    <div className="min-h-screen">
      <Navbar onUploadSuccess={load} />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">

        {/* Header */}
        <div className="rounded-2xl bg-gradient-to-br from-slate-900 to-slate-800 text-white px-6 py-5 shadow-lg flex flex-col gap-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h1 className="text-2xl font-bold tracking-tight">Portfolio Overview</h1>
              <p className="text-sm text-slate-400 mt-0.5">
                {dateRange.date_from && dateRange.date_to
                  ? `${dateRange.date_from} → ${dateRange.date_to}`
                  : `Season-to-date · ${new Date().getFullYear()}`}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button onClick={() => { load(); loadGA() }}
                      className="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-white/10 hover:bg-white/20 text-white text-sm font-medium transition-colors border border-white/10"
                      title="Refresh">
                <RefreshCw size={14} />
              </button>
              <button onClick={openPDF}
                      className="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-white/10 hover:bg-white/20 text-white text-sm font-medium transition-colors border border-white/10"
                      title="PDF Report">
                <FileText size={14} />
                <span className="hidden sm:inline">PDF</span>
              </button>
              <button onClick={downloadXLSX}
                      className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-500 hover:bg-blue-400 text-white text-sm font-medium transition-colors shadow-sm"
                      title="Excel workbook: summary, hotels, weekly & daily raw data">
                <FileSpreadsheet size={14} />
                <span className="hidden sm:inline">Excel</span>
              </button>
              <button onClick={downloadCSV}
                      className="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-white/10 hover:bg-white/20 text-white text-sm font-medium transition-colors border border-white/10"
                      title="Export CSV (hotel KPI table)">
                <FileDown size={14} />
                <span className="hidden sm:inline">CSV</span>
              </button>
            </div>
          </div>
          <DateRangePicker value={dateRange} onChange={setDateRange} />
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
            {error}
          </div>
        )}

        {s && (
          <div className="space-y-5">

            {/* ══ TIER 1 · HOTEL VALUE ══════════════════════════════════════ */}
            <Tier title="Tier 1 · Hotel Value" subtitle="Your product-market fit story" defaultOpen>
              {/* Row 1 — Core hotel value */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <KPICard label="Active Hotels" value={s.total_active_hotels} icon="🏨" colour="blue"
                         onClick={() => setDrillMetric('active_hotels')}
                         breakdown={[
                           { label: 'Class A only',      value: s.class_a_hotels,                                        sub: '≥30 bookings / month',                colour: 'blue'  },
                           { label: 'Class B (incl. A)', value: (s.class_a_hotels || 0) + (s.class_b_hotels || 0),       sub: 'Class B + Class A · ≥15/mo',          colour: 'green' },
                           { label: 'Class C (incl. A+B)', value: s.total_active_hotels,                                 sub: 'Classes C, B & A · ≥3/mo',            colour: 'amber' },
                         ]} />
                <KPICard label="Rooms Live" value={num(s.total_rooms_live)} icon="🛏️" colour="teal"
                         onClick={() => setDrillMetric('rooms_live')}
                         breakdown={[
                           { label: 'Class A only',        value: num(s.rooms_class_a),                                          sub: '≥30 bookings / month',       colour: 'blue'  },
                           { label: 'Class B (incl. A)',   value: num((s.rooms_class_a || 0) + (s.rooms_class_b || 0)),           sub: 'Class B + Class A · ≥15/mo', colour: 'green' },
                           { label: 'Class C (incl. A+B)', value: num(s.total_rooms_live),                                        sub: 'Classes C, B & A · ≥3/mo',   colour: 'amber' },
                         ]} />
                <KPICard label="BG Net Revenue" value={fmt(s.total_net_revenue)} icon="💰" colour="green"
                         onClick={() => setDrillMetric('net_revenue')} />
                <KPICard label="ARPAR_BG" value={fmt2(s.avg_arpar_bg)} icon="📐" colour="violet" sub="Net Rev ÷ Rooms" />
              </div>

              {/* Row 2 — Volume & commercial metrics */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <KPICard label="GMV (Season)" value={fmt(s.total_gmv_season)} icon="📈" colour="indigo"
                         onClick={() => setDrillMetric('gmv')} />
                <KPICard label="Take Rate"          value={pct(s.blended_take_rate)} icon="%" colour="slate" />
                <KPICard label="Direct Booking Uplift"
                         value={pct(s.avg_direct_booking_uplift)} icon="🏷️"
                         colour={s.avg_direct_booking_uplift == null ? 'slate' : 'sky'}
                         sub={s.avg_direct_booking_uplift == null ? 'Upload data to populate' : undefined} />
                <KPICard label="Incremental Rev / Hotel"
                         value={fmt(s.avg_incremental_revenue)} icon="➕"
                         colour={s.avg_incremental_revenue == null ? 'slate' : 'rose'}
                         sub={s.avg_incremental_revenue == null ? 'Upload data to populate' : undefined}
                         split={s.avg_incremental_revenue != null ? {
                           alsabini: s.incremental_revenue_alsabini != null ? fmt(s.incremental_revenue_alsabini) : null,
                           other:    s.incremental_revenue_non_alsabini != null ? fmt(s.incremental_revenue_non_alsabini) : null,
                         } : undefined} />
              </div>

              {/* Row 3 — Engagement + Forecast */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                <KPICard label="Attach Rate"        value={pct(s.portfolio_attach_rate)} icon="🔗"
                         colour={attachColour(s.portfolio_attach_rate)}
                         onClick={() => setDrillMetric('attach_rate')}
                         sub={s.portfolio_attach_rate == null
                           ? 'Paid bookings ÷ rooms (active hotels only) — target >25%'
                           : `Paid bookings ÷ rooms · Active hotels only · ${fmtPeriod(dateRange)} · ${attachInterpret(s.portfolio_attach_rate)}`}
                         breakdown={s.attach_rate_class_a != null ? [
                           { label: 'Class A only',        value: pct(s.attach_rate_class_a), sub: '≥30 bookings / month',       colour: 'blue'  },
                           { label: 'Class B (incl. A)',   value: pct(s.attach_rate_class_b), sub: 'Class B + Class A · ≥15/mo', colour: 'green' },
                           { label: 'Class C (incl. A+B)', value: pct(s.attach_rate_class_c), sub: 'Classes C, B & A · ≥3/mo',   colour: 'amber' },
                         ] : undefined} />

                <KPICard label="Bookings Forecast" icon="🎯" colour="slate"
                         value="📈"
                         onClick={() => setForecastMetric('bookings')}
                         sub="Click here to view graph of weekly forecast" />

                <KPICard label="GMV Forecast" icon="📊" colour="slate"
                         value="📈"
                         onClick={() => setForecastMetric('gmv')}
                         sub="Click here to view graph of weekly forecast" />
              </div>

            </Tier>

            {/* ══ TIER 2 · ENGINE ══════════════════════════════════════════ */}
            <Tier title="Tier 2 · Engine" subtitle="What drives Tier 1" defaultOpen>

              {/* Core Revenue */}
              <div>
                <p className="text-[10px] font-semibold text-slate-300 uppercase tracking-widest mb-2">Core Revenue</p>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                  <KPICard label="Monthly Net Revenue (MNR)" value={fmt(s.saas_mrr)} icon="🔁" colour="green"
                           onClick={() => setDrillMetric('mnr')}
                           sub={`Active Hotels × Avg Monthly Net Revenue per Hotel${s.mrr_growth_rate != null ? ` · ${s.mrr_growth_rate > 0 ? '+' : ''}${pct(s.mrr_growth_rate)} MoM` : ''}`}
                           breakdown={s.saas_mrr_class_a != null ? [
                             { label: 'Class A only',        value: fmt(s.saas_mrr_class_a), sub: '≥30 bookings / month',       colour: 'blue'  },
                             { label: 'Class B (incl. A)',   value: fmt(s.saas_mrr_class_b), sub: 'Class B + Class A · ≥15/mo', colour: 'green' },
                             { label: 'Class C (incl. A+B)', value: fmt(s.saas_mrr),         sub: 'Classes C, B & A · ≥3/mo',   colour: 'amber' },
                           ] : undefined} />
                  <KPICard label="MNR Growth"  value={pct(s.mrr_growth_rate)} icon="📈"
                           colour={s.mrr_growth_rate == null ? 'slate' : s.mrr_growth_rate >= 15 ? 'green' : s.mrr_growth_rate >= 5 ? 'amber' : 'red'}
                           sub="Target: 15–20% MoM" />
                  {/* ── Internal-only metrics ── */}
                  {internalData ? (
                    <KPICard label="Cash Balance" value={fmt(internalData.cash_balance)} icon="🏦" colour="slate" />
                  ) : (
                    <LockedMetricCard label="Cash Balance" icon="🏦" onUnlock={openUnlockForm} />
                  )}
                  {internalData ? (
                    <KPICard label="Runway" value={mo(runway)} icon="⏱️" colour={runwayColour}
                             sub={internalData.monthly_burn_rate ? `Burn: ${fmt(internalData.monthly_burn_rate)}/mo` : undefined} />
                  ) : (
                    <LockedMetricCard label="Runway" icon="⏱️" onUnlock={openUnlockForm} />
                  )}
                  {/* Unlock modal */}
                  {showUnlockForm && (
                    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
                      <form onSubmit={submitInternalToken}
                            className="bg-white rounded-2xl shadow-2xl p-6 w-80 flex flex-col gap-4">
                        <div className="flex items-center gap-2">
                          <Lock size={16} className="text-slate-500" />
                          <span className="font-semibold text-slate-800">Internal Access</span>
                        </div>
                        <p className="text-xs text-slate-500">
                          Cash Balance and Runway are restricted to the BookinGuru team.
                          Enter the internal passcode to view them.
                        </p>
                        <input
                          ref={internalInputRef}
                          type="password"
                          placeholder="Internal passcode"
                          value={internalInput}
                          onChange={e => setInternalInput(e.target.value)}
                          className="border border-slate-200 rounded-lg px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-400"
                        />
                        {internalError && (
                          <p className="text-xs text-red-500">{internalError}</p>
                        )}
                        <div className="flex gap-2 justify-end">
                          <button type="button" onClick={() => setShowUnlockForm(false)}
                                  className="text-xs text-slate-400 hover:text-slate-600 px-3 py-1.5">
                            Cancel
                          </button>
                          <button type="submit" disabled={internalLoading}
                                  className="bg-navy text-white text-xs font-medium px-4 py-1.5 rounded-lg disabled:opacity-60">
                            {internalLoading ? 'Checking…' : 'Unlock'}
                          </button>
                        </div>
                      </form>
                    </div>
                  )}
                </div>
              </div>

              {/* Monetisation */}
              <div>
                <p className="text-[10px] font-semibold text-slate-300 uppercase tracking-widest mb-2">Monetisation</p>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
                  <KPICard label="AOV"                  value={fmt(s.avg_aov)} icon="🛒" colour="sky"
                           onClick={() => setDrillMetric('aov')}
                           sub={s.avg_aov != null && s.total_gmv_season != null
                             ? `€${Number(s.total_gmv_season).toLocaleString('en-EU', {maximumFractionDigits:0})} GMV ÷ ${Number(s.total_paid_transactions).toLocaleString()} paid bookings`
                             : 'Target: €60+'} />
                  <KPICard label="Orders / Guest"        value={dec(s.orders_per_guest, 2)} icon="🛍️"
                           colour={s.orders_per_guest == null ? 'slate' : s.orders_per_guest >= 1.5 ? 'green' : 'amber'}
                           sub={s.orders_per_guest == null ? 'Upload unique_guests column' : 'Target: 1.5–2.5'} />
                  <KPICard label="ARPG"                  value={fmt(s.avg_arpg)} icon="👤"
                           colour={s.avg_arpg == null ? 'slate' : 'indigo'}
                           sub={s.avg_arpg == null ? 'Upload unique_guests column' : 'Revenue / buying guest'} />
                  <KPICard label="Revenue / Booking"     value={fmt(s.revenue_per_booking)} icon="🎫" colour="violet" />
                  <KPICard label="Revenue / Hotel / Mo"  value={fmt(s.revenue_per_hotel_per_month)} icon="🏩" colour="green" />
                </div>

                {/* Purchase Channel — Direct vs Concierge */}
                {s.direct_gmv != null || s.concierge_gmv != null ? (
                  <div className="mt-3 rounded-xl border border-slate-200 bg-white p-4">
                    <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest mb-3">Purchase Channel — GMV &amp; BG Revenue</p>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      <div className="rounded-lg bg-blue-50 border border-blue-100 p-3">
                        <p className="text-[10px] font-semibold text-blue-500 uppercase tracking-wide mb-1">Direct (Catalog)</p>
                        <p className="text-lg font-bold text-slate-800">{fmt(s.direct_gmv)}</p>
                        <p className="text-xs text-slate-500">Rev: {fmt(s.direct_revenue)}</p>
                        {s.direct_pct != null && <p className="text-xs text-blue-400 mt-0.5">{s.direct_pct}% of GMV</p>}
                      </div>
                      <div className="rounded-lg bg-emerald-50 border border-emerald-100 p-3">
                        <p className="text-[10px] font-semibold text-emerald-600 uppercase tracking-wide mb-1">Concierge (Offer)</p>
                        <p className="text-lg font-bold text-slate-800">{fmt(s.concierge_gmv)}</p>
                        <p className="text-xs text-slate-500">Rev: {fmt(s.concierge_revenue)}</p>
                        {s.concierge_pct != null && <p className="text-xs text-emerald-500 mt-0.5">{s.concierge_pct}% of GMV</p>}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="mt-3 rounded-xl border border-dashed border-slate-200 bg-slate-50 p-3 text-xs text-slate-400 text-center">
                    Purchase Channel split — add <code className="bg-slate-100 px-1 rounded">direct_gmv, concierge_gmv</code> columns or re-sync from Sheets
                  </div>
                )}

                {/* Revenue Segment — BG General vs Alsabini */}
                {s.bg_general_revenue != null || s.alsabini_revenue != null ? (
                  <div className="mt-3 rounded-xl border border-slate-200 bg-white p-4">
                    <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest mb-3">Revenue Segment — BG General vs Alsabini</p>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      <div className="rounded-lg bg-violet-50 border border-violet-100 p-3">
                        <p className="text-[10px] font-semibold text-violet-600 uppercase tracking-wide mb-1">BG General</p>
                        <p className="text-lg font-bold text-slate-800">{fmt(s.bg_general_revenue)}</p>
                        {s.bg_general_pct != null && <p className="text-xs text-violet-500 mt-0.5">{s.bg_general_pct}% of revenue</p>}
                      </div>
                      <div className="rounded-lg bg-amber-50 border border-amber-100 p-3 cursor-pointer hover:bg-amber-100 transition-colors"
                           onClick={() => setDrillMetric('alsabini')}>
                        <p className="text-[10px] font-semibold text-amber-600 uppercase tracking-wide mb-1">Alsabini</p>
                        <p className="text-lg font-bold text-slate-800">{fmt(s.alsabini_revenue)}</p>
                        {s.alsabini_pct != null && <p className="text-xs text-amber-500 mt-0.5">{s.alsabini_pct}% of revenue</p>}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="mt-3 rounded-xl border border-dashed border-slate-200 bg-slate-50 p-3 text-xs text-slate-400 text-center">
                    Revenue Segment split — sync from Sheets (2026 data with Alsabini Take column)
                  </div>
                )}

                {/* Vertical Breakdown (raw Column C values) */}
                {s.vertical_breakdown && Object.keys(s.vertical_breakdown).length > 0 ? (
                  <div className="mt-3 rounded-xl border border-slate-200 bg-white p-4">
                    <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest mb-3">Vertical Breakdown — GMV &amp; Net Revenue</p>
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                      {Object.entries(s.vertical_breakdown)
                        .sort(([, a], [, b]) => b.gmv - a.gmv)
                        .map(([vertical, vals]) => (
                          <div key={vertical} className="rounded-lg bg-slate-50 border border-slate-100 p-3">
                            <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide mb-1 capitalize">{vertical}</p>
                            <p className="text-base font-bold text-slate-800">{fmt(vals.gmv)}</p>
                            <p className="text-xs text-slate-500">Rev: {fmt(vals.revenue)}</p>
                            <div className="flex gap-2 mt-1">
                              {vals.gmv_pct != null && <p className="text-[10px] text-blue-400">{vals.gmv_pct}% GMV</p>}
                              {vals.revenue_pct != null && <p className="text-[10px] text-emerald-500">{vals.revenue_pct}% Rev</p>}
                            </div>
                          </div>
                        ))}
                    </div>
                  </div>
                ) : (
                  <div className="mt-3 rounded-xl border border-dashed border-slate-200 bg-slate-50 p-3 text-xs text-slate-400 text-center">
                    Vertical Breakdown — sync from Sheets to populate (uses Column C vertical values)
                  </div>
                )}
              </div>

              {/* Funnel */}
              <div>
                <p className="text-[10px] font-semibold text-slate-300 uppercase tracking-widest mb-2">Funnel</p>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                  <KPICard label="Paid Transactions"   value={num(s.total_paid_transactions)} icon="✅" colour="slate" />
                  <KPICard label="Total Bookings"      value={num(s.total_bookings)} icon="📋" colour="slate" sub="Paid + free" />
                  <KPICard label="Orders / Day"        value={dec(s.orders_per_day, 1)} icon="📅" colour="blue" />
                  <KPICard label="Pre-Arrival Attach"  value={pct(s.pre_arrival_attach_rate)} icon="✈️"
                           colour={s.pre_arrival_attach_rate == null ? 'slate' : 'green'}
                           sub={s.pre_arrival_attach_rate == null ? 'Upload pre_arrival_bookings' : '1–7 days before check-in'} />
                  <KPICard label="Post-Booking Attach" value={pct(s.post_booking_attach_rate)} icon="📩"
                           colour={s.post_booking_attach_rate == null ? 'slate' : 'blue'}
                           sub={s.post_booking_attach_rate == null ? 'Upload post_booking_bookings' : 'Immediately post-confirm'} />
                  <KPICard label="WhatsApp Uplift"     value={s.whatsapp_conversion_uplift != null ? `+${pct(s.whatsapp_conversion_uplift)}` : '—'} icon="💬"
                           colour={s.whatsapp_conversion_uplift == null ? 'slate' : s.whatsapp_conversion_uplift >= 80 ? 'green' : 'amber'}
                           sub={s.whatsapp_conversion_uplift == null ? 'Upload whatsapp_bookings + email_bookings' : 'vs email-only channel'} />
                  <KPICard label="Offers Generated"   value={num(s.total_offers_generated) ?? '—'} icon="🎯"
                           colour={s.total_offers_generated == null ? 'slate' : 'blue'}
                           sub={s.total_offers_generated == null ? 'Upload data to populate' : undefined} />
                  <KPICard label="Offers Conversion"  value={pct(s.avg_offers_conversion)} icon="🔄"
                           colour={s.avg_offers_conversion == null ? 'slate' : 'green'}
                           sub={s.avg_offers_conversion == null ? 'Upload data to populate' : undefined} />
                </div>

                {/* Google Analytics */}
                <div className="mt-3">
                  <GASection data={gaData} loading={gaLoading} />
                </div>

                {/* Placeholder funnel metrics */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
                  <PlaceholderCard label="Time to First Purchase" icon="⏳" source="Booking timing data required" />
                  <PlaceholderCard label="Revenue per Touchpoint" icon="📨" source="Upload communications_sent column" />
                </div>
              </div>
            </Tier>

            {/* ══ TIER 3 · REPEATABILITY ═══════════════════════════════════ */}
            <Tier title="Tier 3 · Repeatability" subtitle="Proves the model works at every hotel, not just the best ones">
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
                <KPICard label="Attach Rate Consistency" value={s.attach_rate_variance != null ? `${dec(s.attach_rate_variance, 1)} pp` : '—'} icon="📊"
                         colour={varColour(s.attach_rate_variance)}
                         sub={s.attach_rate_variance != null
                           ? s.attach_rate_variance < 5  ? 'Excellent — system works uniformly'
                           : s.attach_rate_variance < 10 ? 'Moderate — some hotels outperform others'
                           : 'High — results vary widely across hotels'
                           : 'How evenly guests buy across all hotels · lower = more consistent'} />
                <KPICard label="Revenue / Room Consistency" value={s.arpar_variance != null ? `€${dec(s.arpar_variance, 0)}` : '—'} icon="📉"
                         colour={s.arpar_variance == null ? 'slate' : s.arpar_variance < 5 ? 'green' : s.arpar_variance < 15 ? 'amber' : 'red'}
                         sub={s.arpar_variance != null
                           ? 'Spread in revenue per room across hotels · lower = more predictable'
                           : 'Spread in revenue per room across hotels · lower = more predictable'} />
                <KPICard label="Catalogue Utilisation"   value={pct(s.pct_catalogue_active)} icon="📦"
                         colour={s.pct_catalogue_active == null ? 'slate' : s.pct_catalogue_active >= 60 ? 'green' : s.pct_catalogue_active >= 40 ? 'amber' : 'red'}
                         sub={s.pct_catalogue_active == null
                           ? 'What % of available services are actually being booked · target >60%'
                           : s.pct_catalogue_active >= 60 ? 'Most listed services are generating bookings'
                           : 'Many listed services are not yet converting — room to grow'} />
                <KPICard label="Booking Success Rate"    value={pct(s.fill_rate)} icon="✓"
                         colour={fillColour(s.fill_rate)}
                         sub={s.fill_rate == null
                           ? 'How often a guest who tries to book actually completes it · target >90%'
                           : s.fill_rate >= 90 ? 'Nearly all booking attempts complete successfully'
                           : 'Some guests are abandoning mid-booking — friction in the flow'} />
                <KPICard label="Bookings / Room / Day"   value={s.transactions_per_room_per_day != null ? dec(s.transactions_per_room_per_day, 3) : '—'} icon="🏪"
                         colour={s.transactions_per_room_per_day == null ? 'slate' : s.transactions_per_room_per_day >= 0.15 ? 'green' : s.transactions_per_room_per_day >= 0.05 ? 'amber' : 'red'}
                         sub={s.transactions_per_room_per_day != null
                           ? 'How active each room is on average · target 0.15–0.25 at peak season'
                           : 'Daily booking intensity per room · target 0.15–0.25 at peak season'} />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <PlaceholderCard label="Revenue per Supplier"      icon="🏭" source="Supplier-level data required" />
                <PlaceholderCard label="Top Supplier Dependency %" icon="⚠️" source="Supplier-level data required" />
              </div>
            </Tier>

            {/* ══ TIER 4 · SCALE ═══════════════════════════════════════════ */}
            <Tier title="Tier 4 · Scale" subtitle="Pilots → company">
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
                <KPICard label="New Active Hotels"      value={s.new_active_hotels ?? '—'} icon="🆕" colour="blue" sub="First-time active this period" />
                <KPICard label="Revenue / Hotel / Mo"   value={fmt(s.revenue_per_hotel_per_month)} icon="🏩" colour="green" />
                <KPICard label="Rooms Under Mgmt"       value={num(s.total_rooms_live)} icon="🛏️" colour="slate" />
                <KPICard label="Hotels in Pipeline"     value={s.hotels_in_pipeline ?? '—'} icon="🔄" colour="slate" sub="Signed, not yet active" />
                <KPICard label="Onboarded → Active"     value={pct(s.onboarded_to_active_rate)} icon="✅"
                         colour={s.onboarded_to_active_rate == null ? 'slate' : s.onboarded_to_active_rate >= 70 ? 'green' : s.onboarded_to_active_rate >= 40 ? 'amber' : 'red'}
                         sub="Target: >70%" />
                <KPICard label="NRR"                    value={s.nrr != null ? `${dec(s.nrr, 1)}%` : '—'} icon="🔄"
                         colour={nrrColour(s.nrr)}
                         sub={s.nrr == null ? 'Need 2+ periods of data' : '>100% = growing without new hotels'} />
                <KPICard label="Expansion Revenue"      value={fmt(s.expansion_revenue)} icon="🔗"
                         colour={s.expansion_revenue == null ? 'slate' : 'green'}
                         sub={s.expansion_revenue == null ? 'Mark hotels as chain expansions' : 'From chain 2nd+ properties'} />
                <KPICard label="Expansion Rate"         value={pct(s.expansion_rate)} icon="🏢"
                         colour={s.expansion_rate == null ? 'slate' : s.expansion_rate >= 40 ? 'green' : 'amber'}
                         sub={s.expansion_rate == null ? 'Mark hotels as chain expansions' : '% new supply from chains'} />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <PlaceholderCard label="Time to Expansion (chain)" icon="⏱️" source="Tag hotels with chain group to compute" />
                <PlaceholderCard label="Hotel NPS"                 icon="⭐" source="NPS survey integration required" />
                <PlaceholderCard label="Guest Repeat Usage"        icon="🔁" source="Guest history tracking required" />
              </div>
            </Tier>

            {/* ══ TIER 5 · EFFICIENCY ══════════════════════════════════════ */}
            <Tier title="Tier 5 · Efficiency" subtitle="Determines if you can raise and scale">
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
                <KPICard label="LTV : CAC"          value={s.ltv_cac_ratio != null ? `${dec(s.ltv_cac_ratio, 1)}×` : '—'} icon="📐"
                         colour={s.ltv_cac_ratio == null ? 'slate' : s.ltv_cac_ratio >= 4 ? 'green' : s.ltv_cac_ratio >= 2 ? 'amber' : 'red'}
                         sub={s.ltv_cac_ratio == null ? 'Enter CAC on hotel records' : 'Target: >3×'} />
                <KPICard label="CAC Payback"        value={s.cac_payback_months != null ? `${dec(s.cac_payback_months, 1)} mo` : '—'} icon="📅"
                         colour={s.cac_payback_months == null ? 'slate' : s.cac_payback_months <= 6 ? 'green' : s.cac_payback_months <= 12 ? 'amber' : 'red'}
                         sub={s.cac_payback_months == null ? 'Enter CAC on hotel records' : 'Target: <6 months'} />
                <KPICard label="CAC / Hotel"        value={fmt(s.avg_cac)} icon="💸" colour="slate"
                         sub={s.avg_cac == null ? 'Enter CAC on hotel records' : undefined} />
                <KPICard label="Hotel LTV"          value={fmt(s.hotel_ltv)} icon="💎"
                         colour={s.hotel_ltv == null ? 'slate' : 'green'}
                         sub={s.hotel_ltv == null ? 'Enter CAC on hotel records' : 'Avg Rev × Hotel Lifetime'} />
                <KPICard label="Time to Activate"   value={s.avg_time_to_activate != null ? `${dec(s.avg_time_to_activate, 0)} days` : '—'} icon="⚡"
                         colour={s.avg_time_to_activate == null ? 'slate' : s.avg_time_to_activate <= 21 ? 'green' : s.avg_time_to_activate <= 45 ? 'amber' : 'red'}
                         sub={s.avg_time_to_activate == null ? 'Enter date_signed + date_activated on hotels' : 'Target: <21 days'} />
                <KPICard label="Gross Margin %"     value={pct(s.gross_margin_pct)} icon="📊"
                         colour={s.gross_margin_pct == null ? 'slate' : s.gross_margin_pct >= 75 ? 'green' : s.gross_margin_pct >= 60 ? 'amber' : 'red'}
                         sub={s.gross_margin_pct == null ? 'Enter COGS in Financial Snapshot' : 'Target: >75%'} />
                <KPICard label="Revenue / Employee" value={s.revenue_per_employee != null ? `${fmtK(s.revenue_per_employee)}/yr` : '—'} icon="👥"
                         colour={s.revenue_per_employee == null ? 'slate' : 'blue'}
                         sub={s.revenue_per_employee == null ? 'Enter headcount in Financial Snapshot' : 'Target: €150–300k'} />
                <KPICard label="Hotels in Pipeline" value={s.hotels_in_pipeline ?? '—'} icon="🔄" colour="slate" />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <PlaceholderCard label="Sales Cycle Length"             icon="🗓️" source="CRM integration required (e.g. HubSpot)" />
                <PlaceholderCard label="Contacted → Active Conversion"  icon="📞" source="CRM integration required (e.g. HubSpot)" />
              </div>
            </Tier>

            {/* ══ TIER 6 · MARKETPLACE CONTEXT ═════════════════════════════ */}
            <Tier title="Tier 6 · Marketplace Context" subtitle="Narrative metrics — not for operating decisions">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <KPICard label="Guest GMV (Total Marketplace)" value={fmt(s.total_gmv_season)} icon="🌐" colour="blue"
                         sub="We keep ~5% — never use as health proxy" />
                <KPICard label="Revenue / Booking"  value={fmt(s.revenue_per_booking)} icon="🎫" colour="slate" />
                <KPICard label="Blended Take Rate"  value={pct(s.blended_take_rate)} icon="%" colour="slate" />
              </div>
            </Tier>

          </div>
        )}

        {/* Weekly Insights — what grew / declined sharply vs last week */}
        <WeeklyInsights dateRange={dateRange} />

        {/* Trend Charts */}
        {trendData.length > 0 && (
          <section className="rounded-2xl border border-slate-200/80 bg-white/60 shadow-sm overflow-hidden">
            <div className="px-5 py-3.5 bg-gradient-to-r from-slate-50 to-white border-b border-slate-100">
              <h2 className="text-[11px] font-bold text-slate-500 uppercase tracking-widest">KPI Trends</h2>
            </div>
            <div className="p-5 grid grid-cols-1 lg:grid-cols-2 gap-4">
              <GMVChart         data={trendData} />
              <NetRevenueChart  data={trendData} />
              <AOVChart          data={trendData} />
              <AttachRateChart   data={trendData} />
              <ActiveHotelsChart data={trendData} />
              <TransactionsChart data={trendData} />
              {hotels.length > 0 && (
                <div className="lg:col-span-2">
                  <HotelAOVChart hotels={hotels} />
                </div>
              )}
              <div className="lg:col-span-2">
                <TopVendorsChart dateRange={dateRange} filters={filters} />
              </div>
              <div className="lg:col-span-2">
                <TopProductsChart dateRange={dateRange} filters={filters} />
              </div>
            </div>
          </section>
        )}

        {/* Hotel weekly bookings matrix — between KPI Trends and Hotel Portfolio */}
        <HotelWeeklyMatrix filters={filters} dateRange={dateRange} />

        {/* Filter bar + hotel grid */}
        {(() => {
          const q = hotelSearch.trim().toLowerCase()
          const visibleHotels = q
            ? hotels.filter(h =>
                (h.hotel_name || '').toLowerCase().includes(q) ||
                (h.market || '').toLowerCase().includes(q))
            : hotels
          return (
        <section className="rounded-2xl border border-slate-200/80 bg-white/60 shadow-sm overflow-hidden">
          <div className="px-5 py-3.5 bg-gradient-to-r from-slate-50 to-white border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <h2 className="text-[11px] font-bold text-slate-500 uppercase tracking-widest">
              Hotel Portfolio
              {!loading && (
                <span className="ml-2 text-xs font-normal text-slate-400 normal-case tracking-normal">
                  ({q ? `${visibleHotels.length} of ${hotels.length}` : hotels.length} properties)
                </span>
              )}
            </h2>
            <div className="flex flex-col sm:flex-row sm:items-center gap-2">
              {/* Hotel name search */}
              <div className="relative">
                <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                <input
                  type="text"
                  value={hotelSearch}
                  onChange={e => setHotelSearch(e.target.value)}
                  placeholder="Search hotels…"
                  className="text-xs border border-slate-200 rounded-lg pl-8 pr-7 py-1.5 w-full sm:w-52 bg-white text-slate-700 focus:outline-none focus:ring-1 focus:ring-blue-300 focus:border-blue-300"
                />
                {hotelSearch && (
                  <button
                    onClick={() => setHotelSearch('')}
                    className="absolute right-1.5 top-1/2 -translate-y-1/2 p-0.5 rounded text-slate-400 hover:text-slate-600"
                    aria-label="Clear search"
                  >
                    <X size={13} />
                  </button>
                )}
              </div>
              <FilterBar filters={filters} onChange={handleFilterChange} options={options} />
            </div>
          </div>
          <div className="p-5">

          {loading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="card p-5 animate-pulse">
                  <div className="h-4 bg-slate-200 rounded w-2/3 mb-3" />
                  <div className="h-3 bg-slate-100 rounded w-1/2 mb-4" />
                  <div className="grid grid-cols-2 gap-2">
                    {[...Array(6)].map((_, j) => <div key={j} className="h-8 bg-slate-100 rounded" />)}
                  </div>
                </div>
              ))}
            </div>
          ) : visibleHotels.length === 0 ? (
            <div className="card p-12 text-center text-slate-400">
              <div className="text-4xl mb-3">🏨</div>
              {q ? (
                <>
                  <p className="font-medium">No hotels match “{hotelSearch.trim()}”.</p>
                  <p className="text-sm mt-1">Try a different search or <button onClick={() => setHotelSearch('')} className="text-blue-500 hover:underline">clear it</button>.</p>
                </>
              ) : (
                <>
                  <p className="font-medium">No hotels match your filters.</p>
                  <p className="text-sm mt-1">Try clearing filters or uploading a Weekly KPI file.</p>
                </>
              )}
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {[...visibleHotels]
                .sort((a, b) => {
                  const order = { A: 0, B: 1, C: 2 }
                  return (order[a.activity_class] ?? 3) - (order[b.activity_class] ?? 3)
                })
                .map(h => <HotelCard key={h.hotel_id} hotel={h} />)}
            </div>
          )}
          </div>
        </section>
          )
        })()}
      </main>

      {/* Drill-down trend modal */}
      {drillMetric && (
        <DrillDownModal
          metric={drillMetric}
          trendData={trendData}
          onClose={() => setDrillMetric(null)}
          dateRange={dateRange}
          filters={filters}
        />
      )}

      {/* Forecast modal */}
      {forecastMetric && forecastData && (
        <ForecastModal
          metric={forecastMetric}
          data={forecastMetric === 'bookings' ? forecastData.bookings : forecastData.gmv}
          onClose={() => setForecastMetric(null)}
        />
      )}
    </div>
  )
}

/* ── Google Analytics section ───────────────────────────────────────────────── */
function GASection({ data, loading }) {
  if (loading) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-4 animate-pulse flex gap-4">
        <div className="h-8 w-8 bg-slate-200 rounded" />
        <div className="flex-1 space-y-2">
          <div className="h-3 bg-slate-200 rounded w-1/3" />
          <div className="h-2 bg-slate-100 rounded w-1/2" />
        </div>
      </div>
    )
  }

  if (!data || !data.connected) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4 flex items-center gap-3">
        <WifiOff size={20} className="text-slate-400 shrink-0" />
        <div>
          <p className="text-sm font-semibold text-slate-600">Google Analytics — not connected</p>
          <p className="text-xs text-slate-400 mt-0.5">
            Add <code className="bg-slate-100 px-1 rounded">GA4_CREDENTIALS_JSON</code> to Render environment variables to enable Click → Purchase Conversion and Direct Booking data.
          </p>
        </div>
      </div>
    )
  }

  const pctGA = n => n == null ? '—' : `${Number(n).toFixed(2)}%`
  const numGA = n => n == null ? '—' : Number(n).toLocaleString()

  return (
    <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
      <div className="flex items-start justify-between gap-2 mb-3">
        <div>
          <div className="flex items-center gap-2">
            <Wifi size={14} className="text-emerald-600" />
            <span className="text-xs font-semibold text-emerald-700 uppercase tracking-wide">
              Google Analytics · Last {data.date_range_days} days
            </span>
          </div>
          <p className="text-[10px] text-emerald-600 mt-1 opacity-75">
            A <strong>session</strong> = one visit to the hotel's booking page. Each time a guest opens the page, that's one session — regardless of whether they book.
          </p>
        </div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <GAMetric label="Click → Purchase Conv." value={pctGA(data.click_to_purchase_conversion)}
                  sub={`${numGA(data.total_purchases)} purchases out of all sessions`} />
        <GAMetric label="Direct Sessions %"      value={pctGA(data.direct_session_pct)}
                  sub={`${numGA(data.direct_sessions)} guests arrived directly (typed URL or bookmark)`} />
        <GAMetric label="Total Sessions"         value={numGA(data.total_sessions)}
                  sub="Total page visits (unique + repeat)" />
        <GAMetric label="Total Purchases"        value={numGA(data.total_purchases)}
                  sub="Completed bookings tracked by GA" />
      </div>
    </div>
  )
}

function GAMetric({ label, value, sub }) {
  return (
    <div>
      <div className="text-[10px] text-emerald-600 uppercase tracking-wide font-medium">{label}</div>
      <div className="text-lg font-bold text-emerald-900 mt-0.5">{value}</div>
      {sub && <div className="text-[10px] text-emerald-600 mt-0.5">{sub}</div>}
    </div>
  )
}
