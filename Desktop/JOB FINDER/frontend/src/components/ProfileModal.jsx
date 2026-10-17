import { useState, useEffect, useRef } from 'react'
import { useApp } from '../App'

function initials(name) {
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

export default function ProfileModal() {
  const { profileOpen, setProfileOpen, userProfile, saveUserProfile } = useApp()
  const [form, setForm] = useState(userProfile)
  const [saved, setSaved] = useState(false)
  const overlayRef = useRef(null)

  // Sync form when profile changes externally
  useEffect(() => { setForm(userProfile) }, [userProfile])

  // Close on Escape
  useEffect(() => {
    if (!profileOpen) return
    const handler = e => { if (e.key === 'Escape') setProfileOpen(false) }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [profileOpen, setProfileOpen])

  if (!profileOpen) return null

  function handleSave() {
    if (!form.name.trim()) return
    saveUserProfile({ ...form, name: form.name.trim(), email: form.email.trim(), location: form.location.trim() })
    setSaved(true)
    setTimeout(() => { setSaved(false); setProfileOpen(false) }, 800)
  }

  const ini = initials(form.name || 'U')

  return (
    <>
      {/* Backdrop */}
      <div
        ref={overlayRef}
        className="profile-overlay"
        onClick={e => { if (e.target === overlayRef.current) setProfileOpen(false) }}
      />

      {/* Drawer */}
      <div className="profile-drawer">
        <div className="profile-drawer-header">
          <span className="profile-drawer-title">Edit Profile</span>
          <button className="icon-btn" onClick={() => setProfileOpen(false)} aria-label="Close">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6 6 18M6 6l12 12" strokeLinecap="round"/>
            </svg>
          </button>
        </div>

        {/* Avatar preview */}
        <div className="profile-avatar-wrap">
          <div className="profile-avatar-lg">{ini}</div>
          <div>
            <div className="profile-avatar-name">{form.name || 'Your Name'}</div>
            <div className="profile-avatar-email">{form.email || 'your@email.com'}</div>
          </div>
        </div>

        {/* Fields */}
        <div className="profile-fields">
          <div className="profile-field">
            <label className="profile-label">Full Name *</label>
            <input
              className="profile-input"
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="Your full name"
              maxLength={80}
            />
          </div>

          <div className="profile-field">
            <label className="profile-label">Email</label>
            <input
              className="profile-input"
              type="email"
              value={form.email}
              onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
              placeholder="you@example.com"
              maxLength={120}
            />
          </div>

          <div className="profile-field">
            <label className="profile-label">Location</label>
            <input
              className="profile-input"
              value={form.location}
              onChange={e => setForm(f => ({ ...f, location: e.target.value }))}
              placeholder="City, Country"
              maxLength={80}
            />
          </div>
        </div>

        <div className="profile-actions">
          <button className="btn btn-ghost" onClick={() => setProfileOpen(false)}>Cancel</button>
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={!form.name.trim() || saved}
          >
            {saved ? '✓ Saved' : 'Save changes'}
          </button>
        </div>
      </div>
    </>
  )
}
