import { useNavigate } from 'react-router-dom'
import { TrendingUp, MapPin } from 'lucide-react'

const fmt = (n) => n == null ? '—' : `€${Number(n).toLocaleString('en-EU', { maximumFractionDigits: 0 })}`
const pct = (n) => n == null ? '—' : `${Number(n).toFixed(1)}%`

export default function HotelCard({ hotel }) {
  const navigate = useNavigate()

  // Activity class badge — Class A / B / C / Inactive
  const classBadgeStyle = {
    A: 'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700',
    B: 'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700',
    C: 'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700',
  }
  const activityBadge = hotel.activity_class
    ? classBadgeStyle[hotel.activity_class] || 'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-500'
    : 'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-500'
  const activityLabel = hotel.activity_class
    ? `Class ${hotel.activity_class}`
    : '○ Inactive'

  // CRM/pipeline status shown only when not the default "Active" to avoid confusion
  const showCrmBadge = hotel.pipeline_status && hotel.pipeline_status !== 'Active'
  const crmBadgeClass = {
    Pipeline: 'badge-pipeline',
    Churned:  'badge-churned',
  }[hotel.pipeline_status] || 'badge'

  return (
    <div
      onClick={() => navigate(`/hotels/${hotel.hotel_id}`)}
      className="card p-5 cursor-pointer hover:shadow-md hover:border-blue-200 transition-all group"
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <h3 className="font-semibold text-slate-900 truncate group-hover:text-blue-600 transition-colors">
              {hotel.hotel_name}
            </h3>
            {hotel.is_alsabini && (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-100 text-amber-700 shrink-0">
                Alsabini
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5 text-xs text-slate-500 mt-0.5">
            <MapPin size={11} />
            <span>{hotel.market}</span>
            <span className="text-slate-300">·</span>
            <span>{hotel.property_type}</span>
          </div>
        </div>
        {/* Right-side badges */}
        <div className="flex flex-col items-end gap-1 shrink-0 ml-2">
          <div className="flex flex-col items-end gap-0.5">
            <span className={activityBadge}>{activityLabel}</span>
            {hotel.activity_class && (
              <span className="text-[9px] text-slate-400 leading-tight">
                {hotel.activity_class === 'A' ? '≥30 bookings / month'
                 : hotel.activity_class === 'B' ? '≥15 bookings / month'
                 : '≥3 bookings / month'}
              </span>
            )}
          </div>
          {showCrmBadge && <span className={crmBadgeClass}>{hotel.pipeline_status}</span>}
        </div>
      </div>

      {/* Core metrics — always present */}
      <div className="grid grid-cols-2 gap-3">
        <Metric label="Net Revenue"  value={fmt(hotel.net_revenue)} />
        <Metric label="GMV"          value={fmt(hotel.total_gmv)} />
        <Metric label="ARPAR_BG"     value={fmt(hotel.arpar_bg)} />
        <Metric label="AOV"          value={fmt(hotel.aov)} />
        <Metric label="Attach Rate"  value={pct(hotel.attach_rate)} />
        <Metric label="Take Rate"    value={pct(hotel.avg_take_rate)} />
      </div>

      {/* Bookings row */}
      <div className="grid grid-cols-3 gap-2 mt-2 pt-2 border-t border-slate-100">
        <Metric label="Paid Txns"    value={hotel.total_transactions?.toLocaleString()} small />
        <Metric label="Total Bkgs"   value={hotel.total_bookings?.toLocaleString()} small />
        <Metric label="Rooms"        value={hotel.room_count} small />
      </div>

      {/* Optional new metrics — only shown when data uploaded */}
      {(hotel.avg_direct_booking_uplift != null || hotel.total_offers_generated != null || hotel.avg_offers_conversion != null || hotel.avg_incremental_revenue != null) && (
        <div className="grid grid-cols-2 gap-2 mt-2 pt-2 border-t border-slate-100">
          {hotel.avg_incremental_revenue  != null && <Metric label="Incr. Revenue"   value={fmt(hotel.avg_incremental_revenue)} small />}
          {hotel.avg_direct_booking_uplift != null && <Metric label="Direct Uplift %" value={pct(hotel.avg_direct_booking_uplift)} small />}
          {hotel.total_offers_generated   != null && <Metric label="Offers Gen."     value={hotel.total_offers_generated?.toLocaleString()} small />}
          {hotel.avg_offers_conversion    != null && <Metric label="Offers Conv."    value={pct(hotel.avg_offers_conversion)} small />}
        </div>
      )}

      {hotel.saas_mrr > 0 && (
        <div className="mt-3 pt-3 border-t border-slate-100 text-xs text-slate-500 flex items-center gap-1">
          <TrendingUp size={11} className="text-emerald-500" />
          SaaS MRR: <span className="font-medium text-slate-700">{fmt(hotel.saas_mrr)}</span>
        </div>
      )}
    </div>
  )
}

function Metric({ label, value, small }) {
  return (
    <div>
      <div className={`text-slate-400 uppercase tracking-wide ${small ? 'text-[10px]' : 'text-xs'}`}>{label}</div>
      <div className={`font-semibold text-slate-800 mt-0.5 ${small ? 'text-xs' : 'text-sm'}`}>{value ?? '—'}</div>
    </div>
  )
}
