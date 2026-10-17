import { useLocation, useNavigate } from 'react-router-dom'
import { useApp } from '../App'

const pageTitles = {
  '/':       'Dashboard',
  '/jobs':   'Find Jobs',
  '/saved':  'Saved Jobs',
  '/alerts': 'Alerts',
}

function BellIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M15 17H20L18.6 15.6A1.5 1.5 0 0118 14.5V11A6 6 0 006 11v3.5c0 .4-.2.8-.6 1.1L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  )
}

function avatarInitials(name) {
  const parts = (name || '').trim().split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

function TopBar() {
  const location = useLocation()
  const navigate  = useNavigate()
  const { userProfile, setProfileOpen } = useApp()

  const titleKey = Object.keys(pageTitles).find(k =>
    k === '/' ? location.pathname === '/' : location.pathname.startsWith(k)
  )
  const title = pageTitles[titleKey] ?? 'AI Job Finder'

  function handleSearch(e) {
    if (e.key === 'Enter' && e.target.value.trim()) {
      navigate(`/jobs?q=${encodeURIComponent(e.target.value.trim())}`)
    }
  }

  const ini = avatarInitials(userProfile?.name || 'HA')

  return (
    <header className="topbar">
      <div className="topbar-left">
        <h1 className="page-title">{title}</h1>
      </div>

      <div className="topbar-search">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#94A3B8" strokeWidth="2">
          <circle cx="11" cy="11" r="7"/><path d="m21 21-4.35-4.35" strokeLinecap="round"/>
        </svg>
        <input placeholder="Search jobs, companies, skills…" onKeyDown={handleSearch} />
      </div>

      <div className="topbar-right">
        <button className="icon-btn" title="Notifications">
          <BellIcon />
          <span className="notif-dot" />
        </button>
        <div
          className="topbar-avatar"
          title="Edit profile"
          onClick={() => setProfileOpen(true)}
          style={{ cursor: 'pointer' }}
        >
          {ini}
        </div>
      </div>
    </header>
  )
}

export default TopBar
