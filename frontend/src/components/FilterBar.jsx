import { X } from 'lucide-react'

export default function FilterBar({ filters, onChange, options }) {
  function set(key, val) {
    onChange({ ...filters, [key]: val || undefined })
  }

  function setBool(key, val) {
    // val: '' = all, 'true' / 'false' as string — FastAPI parses booleans from query params
    const next = { ...filters }
    if (val === '') delete next[key]
    else next[key] = val
    onChange(next)
  }

  const boolVal = (key) =>
    filters[key] === true  || filters[key] === 'true'  ? 'true'  :
    filters[key] === false || filters[key] === 'false' ? 'false' : ''

  const hasFilters = Object.values(filters).some(v => v !== undefined && v !== '')

  return (
    <div className="flex flex-wrap items-center gap-2">
      {/* Activity class filter — A/B/C/Inactive */}
      <select
        value={filters.activity_class || ''}
        onChange={e => set('activity_class', e.target.value)}
        className="text-sm border border-slate-200 rounded-lg px-3 py-1.5 bg-white
                   text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500
                   focus:border-transparent cursor-pointer"
      >
        <option value="">All Activity</option>
        <option value="A">Class A (≥30/mo)</option>
        <option value="B">Class B (≥15/mo)</option>
        <option value="C">Class C (≥3/mo)</option>
        <option value="inactive">Inactive</option>
      </select>

      <Select
        value={filters.market || ''}
        onChange={v => set('market', v)}
        options={options.markets || []}
        placeholder="All Markets"
      />
      <Select
        value={filters.property_type || ''}
        onChange={v => set('property_type', v)}
        options={options.property_types || []}
        placeholder="All Types"
      />

      {/* Alsabini toggle */}
      <select
        value={boolVal('is_alsabini')}
        onChange={e => setBool('is_alsabini', e.target.value)}
        className="text-sm border border-slate-200 rounded-lg px-3 py-1.5 bg-white
                   text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500
                   focus:border-transparent cursor-pointer"
      >
        <option value="">All Hotels</option>
        <option value="true">Alsabini</option>
        <option value="false">Non-Alsabini</option>
      </select>

      {hasFilters && (
        <button
          onClick={() => onChange({})}
          className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-red-500 transition-colors"
        >
          <X size={13} /> Clear
        </button>
      )}
    </div>
  )
}

function Select({ value, onChange, options, placeholder }) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className="text-sm border border-slate-200 rounded-lg px-3 py-1.5 bg-white
                 text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500
                 focus:border-transparent cursor-pointer"
    >
      <option value="">{placeholder}</option>
      {options.map(o => (
        <option key={o} value={o}>{o}</option>
      ))}
    </select>
  )
}
