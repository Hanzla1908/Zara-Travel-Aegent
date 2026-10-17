import { NavLink } from 'react-router-dom'
import { useApp } from '../App'

const navItems = [
  {
    to: '/', label: 'Dashboard',
    icon: (
      <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M3 12l9-9 9 9M5 10v9a1 1 0 001 1h4v-5h4v5h4a1 1 0 001-1v-9" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    ),
  },
  {
    to: '/jobs', label: 'Find Jobs',
    icon: (
      <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <circle cx="11" cy="11" r="7"/><path d="m21 21-4.35-4.35" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    to: '/saved', label: 'Saved Jobs',
    icon: (
      <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    ),
  },
  {
    to: '/alerts', label: 'Alerts',
    icon: (
      <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M15 17H20L18.6 15.6A1.5 1.5 0 0118 14.5V11A6 6 0 006 11v3.5c0 .4-.2.8-.6 1.1L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    ),
  },
]

function sidebarInitials(name) {
  const parts = (name || '').trim().split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

function Sidebar() {
  const { savedIds, userProfile, setProfileOpen, setSettingsOpen } = useApp()
  const savedCount = savedIds.size
  const name  = userProfile?.name  || 'Hanzla Arif'
  const email = userProfile?.email || 'hanzla90@gmail.com'
  const ini   = sidebarInitials(name)

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-mark">AI</div>
        <div>
          <div className="logo-text">JobFinder</div>
          <div className="logo-sub">AI-POWERED</div>
        </div>
      </div>

      <nav className="sidebar-nav">
        <div className="nav-section-label">Menu</div>

        {navItems.map(item => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
          >
            {item.icon}
            <span style={{ flex: 1 }}>{item.label}</span>
            {item.to === '/saved' && savedCount > 0 && (
              <span className="nav-badge">{savedCount}</span>
            )}
          </NavLink>
        ))}

        <div className="nav-section-label">Account</div>
        <div className="nav-item" onClick={() => setProfileOpen(true)} style={{ cursor: 'pointer' }}>
          <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" strokeLinecap="round"/>
          </svg>
          Profile
        </div>
        <div className="nav-item" onClick={() => setSettingsOpen(true)} style={{ cursor: 'pointer' }}>
          <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <circle cx="12" cy="12" r="3"/>
            <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" strokeLinecap="round"/>
          </svg>
          Settings
        </div>
      </nav>

      <div className="sidebar-footer">
        <div className="user-card" onClick={() => setProfileOpen(true)} style={{ cursor: 'pointer' }} title="Edit profile">
          <div className="user-avatar">{ini}</div>
          <div>
            <div className="user-name">{name}</div>
            <div className="user-email">{email}</div>
          </div>
        </div>
      </div>
    </aside>
  )
}

export default Sidebar
