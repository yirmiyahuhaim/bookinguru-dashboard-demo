import { useNavigate } from 'react-router-dom'
import { clearCredentials } from '../api/client'
import { LogOut, Upload, Trash2, BedDouble, Menu, X, RefreshCw, Bell } from 'lucide-react'
import { useRef, useState } from 'react'
import { api } from '../api/client'
import client from '../api/client'
import BrandMark from './BrandMark'

export default function Navbar({ onUploadSuccess }) {
  const navigate  = useNavigate()
  const fileRef   = useRef()
  const roomsRef  = useRef()
  const [menuOpen, setMenuOpen]   = useState(false)
  const [syncing,  setSyncing]    = useState(false)
  const [alertsOpen, setAlertsOpen] = useState(false)
  const [alertEmail, setAlertEmail] = useState('')
  const [alertMsg, setAlertMsg]     = useState(null)   // { ok, text }
  const [alertBusy, setAlertBusy]   = useState(false)

  async function handleSubscribe(e) {
    e.preventDefault()
    const email = alertEmail.trim()
    if (!email) return
    setAlertBusy(true); setAlertMsg(null)
    try {
      const res = await api.subscribeAlerts(email)
      const s = res.data?.status
      const text = s === 'already_subscribed'
        ? 'That email is already on the alerts list.'
        : s === 'resubscribed'
          ? 'Re-subscribed — you\'re back on the alerts list.'
          : 'Done! You\'ll get an email when a key threshold is hit.'
      setAlertMsg({ ok: true, text })
      setAlertEmail('')
    } catch (err) {
      setAlertMsg({ ok: false, text: err.response?.data?.detail || err.message || 'Could not register.' })
    } finally {
      setAlertBusy(false)
    }
  }

  function logout() {
    clearCredentials()
    navigate('/login')
  }

  async function handleFile(e) {
    const file = e.target.files[0]
    if (!file) return
    setMenuOpen(false)
    try {
      const res = await api.uploadKPI(file)
      const { rows_inserted, warnings, errors } = res.data
      const msgs = [`✓ Inserted ${rows_inserted} rows.`]
      if (warnings.length) msgs.push(...warnings.slice(0, 3))
      if (errors.length)   msgs.push(...errors.slice(0, 3))
      alert(msgs.join('\n'))
      onUploadSuccess?.()
    } catch (err) {
      alert('Upload failed: ' + (err.response?.data?.detail || err.message))
    }
    e.target.value = ''
  }

  async function handleRoomsFile(e) {
    const file = e.target.files[0]
    if (!file) return
    setMenuOpen(false)
    try {
      const res = await api.syncRooms(file)
      const { updated, skipped, unmatched, updates } = res.data
      const lines = [`✓ Hotel metadata synced — ${updated} updated, ${skipped} already correct, ${unmatched} unmatched.`]
      if (updates?.length) {
        lines.push('\nUpdated:')
        updates.slice(0, 8).forEach(u => {
          const roomPart = u.old_rooms !== u.new_rooms ? ` rooms: ${u.old_rooms}→${u.new_rooms}` : ''
          const typePart = u.new_type && u.old_type !== u.new_type ? ` type: "${u.new_type}"` : ''
          lines.push(`  • ${u.hotel_name}:${roomPart}${typePart} (matched "${u.matched_to}", score ${u.score})`)
        })
        if (updates.length > 8) lines.push(`  … and ${updates.length - 8} more`)
      }
      alert(lines.join('\n'))
      onUploadSuccess?.()
    } catch (err) {
      alert('Sync failed: ' + (err.response?.data?.detail || err.message))
    }
    e.target.value = ''
  }

  async function handleSyncSheets() {
    setMenuOpen(false)
    setSyncing(true)
    try {
      await api.syncSheets()
    } catch (err) {
      alert('Sync failed to start: ' + (err.response?.data?.detail || err.message))
      setSyncing(false)
      return
    }

    // Poll until the background task finishes
    const poll = async () => {
      try {
        const { data } = await api.syncStatus()
        if (data.status === 'running') {
          setTimeout(poll, 5000)
          return
        }
        // done or error
        setSyncing(false)
        onUploadSuccess?.()
        const lines = []
        if (data.status === 'error' && !data.warnings?.length) {
          lines.push('✗ Sync failed.')
        } else {
          lines.push('✓ Sync complete.')
        }
        if (data.warnings?.length) lines.push('', ...data.warnings)
        if (data.errors?.length)   lines.push('', 'Errors:', ...data.errors)
        alert(lines.join('\n'))
      } catch {
        // poll request itself failed (e.g. Render sleeping) — keep trying
        setTimeout(poll, 8000)
      }
    }
    setTimeout(poll, 5000)
  }

  async function handleReset() {
    setMenuOpen(false)
    const confirmed = window.confirm(
      '⚠️ This will delete ALL hotels, performance data and financial snapshots.\n\nAre you sure?'
    )
    if (!confirmed) return
    try {
      await client.delete('/upload/reset')
      alert('✓ Database cleared successfully.')
      onUploadSuccess?.()
    } catch (err) {
      alert('Reset failed: ' + (err.response?.data?.detail || err.message))
    }
  }

  return (
    <header className="relative z-50 text-white shadow-xl"
            style={{ background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 60%, #0f2a3f 100%)' }}>
      {/* Bottom accent line */}
      <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-gradient-to-r from-blue-500 via-indigo-400 to-teal-400 opacity-70" />

      {/* Single set of hidden file inputs — always mounted, shared by desktop + mobile */}
      <input ref={fileRef}  type="file" accept=".xlsx,.csv" className="hidden" onChange={handleFile} />
      <input ref={roomsRef} type="file" accept=".xlsx"      className="hidden" onChange={handleRoomsFile} />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <BrandMark size={34} />
          <div className="flex items-center gap-2">
            <span className="hidden sm:block w-px h-3.5 bg-white/20" />
            <span className="text-slate-400 text-xs hidden sm:block font-medium tracking-wide uppercase">Investor Dashboard</span>
          </div>
        </div>

        {/* Desktop action buttons */}
        <div className="hidden sm:flex items-center gap-2">
          <button
            onClick={() => { setAlertMsg(null); setAlertsOpen(true) }}
            className="btn-secondary text-amber-600 hover:text-amber-700 font-semibold"
            title="Get emailed when key milestones / thresholds are hit"
          >
            <Bell size={15} /> Register for Alerts
          </button>
          <button
            onClick={handleSyncSheets}
            disabled={syncing}
            className="btn-secondary text-emerald-700 disabled:opacity-60 disabled:cursor-wait"
            title="Pull the latest bookings from BookinGuru (also runs automatically every 5 min)"
          >
            <RefreshCw size={15} className={syncing ? 'animate-spin' : ''} />
            {syncing ? 'Syncing…' : 'Sync Data'}
          </button>
          <button onClick={() => fileRef.current.click()} className="btn-secondary text-slate-700" title="Upload weekly KPI data">
            <Upload size={15} /> Upload KPI
          </button>
          <button onClick={() => roomsRef.current.click()} className="btn-secondary text-slate-700" title="Sync room counts from hotel list Excel">
            <BedDouble size={15} /> Sync Rooms
          </button>
          <button onClick={handleReset} className="btn-secondary text-red-600 hover:text-red-700">
            <Trash2 size={15} /> Reset DB
          </button>
          <button onClick={logout} className="btn-secondary text-slate-700">
            <LogOut size={15} /> Logout
          </button>
        </div>

        {/* Mobile hamburger */}
        <button
          onClick={() => setMenuOpen(v => !v)}
          className="sm:hidden p-2 rounded-lg text-slate-300 hover:text-white hover:bg-white/10 transition-colors"
          aria-label="Menu"
        >
          {menuOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      {/* Mobile dropdown menu */}
      {menuOpen && (
        <div className="sm:hidden absolute top-14 left-0 right-0 border-t border-white/10 shadow-xl"
             style={{ background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)' }}>

          <div className="px-4 py-3 space-y-1">
            <MobileMenuBtn icon={<Bell size={16} />} label="Register for Alerts" onClick={() => { setMenuOpen(false); setAlertMsg(null); setAlertsOpen(true) }} />
            <MobileMenuBtn icon={<RefreshCw size={16} className={syncing ? 'animate-spin' : ''} />} label={syncing ? 'Syncing…' : 'Sync Data'} onClick={handleSyncSheets} />
            <MobileMenuBtn icon={<Upload size={16} />} label="Upload KPI" onClick={() => fileRef.current.click()} />
            <MobileMenuBtn icon={<BedDouble size={16} />} label="Sync Rooms" onClick={() => roomsRef.current.click()} />
            <MobileMenuBtn icon={<Trash2 size={16} />} label="Reset Database" onClick={handleReset} danger />
            <MobileMenuBtn icon={<LogOut size={16} />} label="Logout" onClick={() => { setMenuOpen(false); logout() }} />
          </div>
        </div>
      )}

      {/* Register for Alerts modal */}
      {alertsOpen && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
          onClick={() => setAlertsOpen(false)}
        >
          <div
            className="bg-white rounded-2xl shadow-2xl w-full max-w-md text-slate-800"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-start justify-between px-5 py-4 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Bell size={16} className="text-amber-500" />
                <h3 className="font-bold text-slate-800 text-base">Register for Alerts</h3>
              </div>
              <button onClick={() => setAlertsOpen(false)} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600">
                <X size={15} />
              </button>
            </div>

            <form onSubmit={handleSubscribe} className="px-5 py-4">
              <p className="text-xs text-slate-500 mb-3 leading-relaxed">
                Get an email after the weekly sync when a key threshold is hit:
              </p>
              <ul className="text-[11px] text-slate-500 mb-4 space-y-1 list-disc pl-4">
                <li>Runway drops below 9 months</li>
                <li>GMV crosses €1M · SaaS MRR hits €5K</li>
                <li>A hotel goes inactive (churn signal)</li>
                <li>Weekly GMV drops more than 20% vs the prior week</li>
              </ul>
              <input
                type="email"
                required
                value={alertEmail}
                onChange={e => setAlertEmail(e.target.value)}
                placeholder="you@company.com"
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-amber-300"
              />
              {alertMsg && (
                <p className={`text-xs mt-2 ${alertMsg.ok ? 'text-emerald-600' : 'text-red-500'}`}>
                  {alertMsg.text}
                </p>
              )}
              <button
                type="submit"
                disabled={alertBusy}
                className="mt-4 w-full bg-amber-500 hover:bg-amber-600 disabled:opacity-60 text-white text-sm font-semibold rounded-lg py-2 transition-colors"
              >
                {alertBusy ? 'Registering…' : 'Register'}
              </button>
              <p className="text-[10px] text-slate-400 mt-2 text-center">
                You can unsubscribe anytime via the link in any alert email.
              </p>
            </form>
          </div>
        </div>
      )}
    </header>
  )
}

function MobileMenuBtn({ icon, label, onClick, danger }) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors
        ${danger
          ? 'text-red-400 hover:bg-red-900/30 hover:text-red-300'
          : 'text-slate-200 hover:bg-white/10 hover:text-white'
        }`}
    >
      {icon}
      {label}
    </button>
  )
}
