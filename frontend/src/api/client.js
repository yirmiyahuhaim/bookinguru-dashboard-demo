import axios from 'axios'

const RENDER_URL = 'https://bookinguru-dashboard.onrender.com'
const BASE = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api`
  : `${RENDER_URL}/api`
// Absolute API base — use for direct browser downloads (window.open / <a> href),
// which must bypass Vercel's SPA rewrite and hit the backend directly.
export const API_BASE = BASE
const client = axios.create({ baseURL: BASE, timeout: 60000 })

// Auth disabled for demo deployment — credentials checked on login page only


export function setCredentials(username, password) {
  const encoded = btoa(`${username}:${password}`)
  sessionStorage.setItem('bg_creds', encoded)
}

export function clearCredentials() {
  sessionStorage.removeItem('bg_creds')
}

export function hasCredentials() {
  return !!sessionStorage.getItem('bg_creds')
}

// ── API helpers ──────────────────────────────────────────────────────────────

export const api = {
  health: () => client.get('/health'),

  // Portfolio
  summary: (filters = {}) => client.get('/financial/summary', { params: filters }),
  trend:   (filters = {}) => client.get('/financial/portfolio-trend', { params: filters }),
  attachRateMonthly: (filters = {}) => client.get('/financial/attach-rate-monthly', { params: filters }),
  topVendors:        (filters = {}) => client.get('/financial/top-vendors', { params: filters }),
  hotelTopVendors:   (hotelId, limit = 3, dateRange = {}) => client.get('/financial/top-vendors', { params: { hotel_id: hotelId, limit, ...dateRange } }),
  vendorProducts:    (vendor, filters = {}) => client.get('/financial/vendor-products', { params: { vendor, ...filters } }),
  vendorWeekly:      (hotelId, dateRange = {}) => client.get('/financial/vendor-weekly', { params: { hotel_id: hotelId, limit: 5, ...dateRange } }),
  vendorHotels:              (vendor, filters = {}) => client.get('/financial/vendor-hotels', { params: { vendor, ...filters } }),
  vendorWeeklyPerformance:   (vendor, filters = {}) => client.get('/financial/vendor-weekly-performance', { params: { vendor, ...filters } }),
  topProducts:               (filters = {}) => client.get('/financial/top-products', { params: filters }),
  productWeeklyPerformance:  (product, vendor, filters = {}) => client.get('/financial/product-weekly-performance', { params: { product, vendor, ...filters } }),
  filters: () => client.get('/hotels/meta/filters'),

  // Hotels
  hotels: (filters = {}) => client.get('/hotels/', { params: filters }),
  hotel:  (id, params = {}) => client.get(`/hotels/${id}`, { params }),

  // Financial
  snapshots: () => client.get('/financial/snapshots'),

  // Upload
  uploadKPI: (file) => {
    const form = new FormData()
    form.append('file', file)
    return client.post('/upload/weekly-kpi', form)
  },

  syncRooms: (file) => {
    const form = new FormData()
    form.append('file', file)
    return client.post('/upload/hotel-meta', form)
  },

  syncSheets:  () => client.post('/upload/sync-sheets', null, { timeout: 30000 }),
  syncStatus: () => client.get('/upload/sync-status', { timeout: 10000 }),

  subscribeAlerts: (email) => client.post('/alerts/subscribe', { email }),

  forecast: () => client.get('/financial/forecast'),                                  // uses 60s default — survives a cold start
  weeklyInsights: (filters = {}) => client.get('/financial/weekly-insights', { params: filters }),
  hotelWeeklyMatrix: (filters = {}) => client.get('/financial/hotel-weekly-matrix', { params: filters }),

  internalMetrics: (token) => client.get('/financial/internal-metrics', {
    headers: { 'X-Internal-Token': token },
  }),

  // Google Analytics
  ga4: (days = 30) => client.get('/analytics/ga4', { params: { days } }),

  // Reports — absolute URLs so direct downloads hit the backend, not the SPA rewrite
  csvUrl: (filters = {}) => {
    const params = new URLSearchParams(filters).toString()
    return `${BASE}/reports/csv${params ? '?' + params : ''}`
  },
  pdfUrl: (filters = {}) => {
    const params = new URLSearchParams(filters).toString()
    return `${BASE}/reports/pdf${params ? '?' + params : ''}`
  },
}

export default client
