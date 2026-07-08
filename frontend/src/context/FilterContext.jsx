import { createContext, useContext, useState, useCallback } from 'react'

const DEFAULT_RANGE = {
  date_from: `${new Date().getFullYear()}-03-01`,
  date_to:   `${new Date().getFullYear()}-10-31`,
}

const FilterContext = createContext(null)

function getInitialRange() {
  try {
    const stored = sessionStorage.getItem('bg_dateRange')
    if (stored) return JSON.parse(stored)
  } catch {}
  return DEFAULT_RANGE
}

export function FilterProvider({ children }) {
  const [dateRange, _setDateRange] = useState(getInitialRange)

  const setDateRange = useCallback((range) => {
    _setDateRange(range)
    try { sessionStorage.setItem('bg_dateRange', JSON.stringify(range)) } catch {}
  }, [])

  return (
    <FilterContext.Provider value={{ dateRange, setDateRange }}>
      {children}
    </FilterContext.Provider>
  )
}

export function useFilters() {
  return useContext(FilterContext)
}
