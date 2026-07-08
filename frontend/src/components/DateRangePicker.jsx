import { useState } from 'react'
import { Calendar } from 'lucide-react'

const today = () => new Date().toISOString().split('T')[0]
const daysAgo = n => {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().split('T')[0]
}

const PRESETS = [
  { label: 'Last 30d',  getRange: () => ({ date_from: daysAgo(30),  date_to: today() }) },
  { label: 'Last 90d',  getRange: () => ({ date_from: daysAgo(90),  date_to: today() }) },
  { label: 'Last 6mo',  getRange: () => ({ date_from: daysAgo(180), date_to: today() }) },
  { label: 'Last 12mo', getRange: () => ({ date_from: daysAgo(365), date_to: today() }) },
  { label: 'Current Season',  getRange: () => ({ date_from: `${new Date().getFullYear()}-03-01`,     date_to: `${new Date().getFullYear()}-10-31`     }) },
  { label: 'Prev Season',     getRange: () => ({ date_from: `${new Date().getFullYear() - 1}-03-01`, date_to: `${new Date().getFullYear() - 1}-10-31` }) },
  { label: 'All time',  getRange: () => ({ date_from: null, date_to: null }) },
]

export default function DateRangePicker({ value, onChange }) {
  const [showCustom, setShowCustom] = useState(false)
  const [active, setActive] = useState('Current Season')

  function selectPreset(preset) {
    setActive(preset.label)
    setShowCustom(false)
    onChange(preset.getRange())
  }

  function toggleCustom() {
    setShowCustom(v => !v)
    setActive('Custom')
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {PRESETS.map(p => (
        <button
          key={p.label}
          onClick={() => selectPreset(p)}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            active === p.label
              ? 'bg-blue-600 text-white shadow-sm'
              : 'bg-white border border-slate-200 text-slate-600 hover:border-blue-300 hover:text-blue-600'
          }`}
        >
          {p.label}
        </button>
      ))}

      <button
        onClick={toggleCustom}
        className={`px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1 transition-colors ${
          active === 'Custom'
            ? 'bg-blue-600 text-white shadow-sm'
            : 'bg-white border border-slate-200 text-slate-600 hover:border-blue-300 hover:text-blue-600'
        }`}
      >
        <Calendar size={11} /> Custom
      </button>

      {showCustom && (
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-1.5 w-full sm:w-auto">
          <input
            type="date"
            value={value.date_from || ''}
            onChange={e => onChange({ ...value, date_from: e.target.value || null })}
            className="w-full sm:w-auto text-xs border border-slate-200 rounded-lg px-2 py-1.5 bg-white
                       text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <span className="text-xs text-slate-400 hidden sm:block">→</span>
          <input
            type="date"
            value={value.date_to || ''}
            onChange={e => onChange({ ...value, date_to: e.target.value || null })}
            className="w-full sm:w-auto text-xs border border-slate-200 rounded-lg px-2 py-1.5 bg-white
                       text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      )}
    </div>
  )
}
