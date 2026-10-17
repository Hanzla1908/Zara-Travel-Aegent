import { useState, useEffect, useRef } from 'react'
import { useApp } from '../App'

const _SETTINGS_KEY = 'jf_settings'
const _DEFAULT_SETTINGS = {
  emailNotifications: false,
  alertSoundEnabled: false,
  defaultResultsLimit: 20,
  autoRefreshAlerts: false,
}

export function loadSettings() {
  try { return { ..._DEFAULT_SETTINGS, ...JSON.parse(localStorage.getItem(_SETTINGS_KEY)) } }
  catch { return { ..._DEFAULT_SETTINGS } }
}

function saveSettings(s) {
  try { localStorage.setItem(_SETTINGS_KEY, JSON.stringify(s)) } catch {}
}

function Toggle({ checked, onChange, label, description }) {
  return (
    <div className="settings-row">
      <div className="settings-row-text">
        <span className="settings-row-label">{label}</span>
        {description && <span className="settings-row-desc">{description}</span>}
      </div>
      <button
        className={`settings-toggle${checked ? ' on' : ''}`}
        onClick={() => onChange(!checked)}
        role="switch"
        aria-checked={checked}
      >
        <span className="settings-toggle-thumb" />
      </button>
    </div>
  )
}

function Select({ value, onChange, label, options }) {
  return (
    <div className="settings-row">
      <span className="settings-row-label">{label}</span>
      <select
        className="settings-select"
        value={value}
        onChange={e => onChange(Number(e.target.value))}
      >
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  )
}

export default function SettingsModal() {
  const { settingsOpen, setSettingsOpen } = useApp()
  const [form, setForm] = useState(loadSettings)
  const [saved, setSaved] = useState(false)
  const overlayRef = useRef(null)

  useEffect(() => {
    if (!settingsOpen) return
    const handler = e => { if (e.key === 'Escape') setSettingsOpen(false) }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [settingsOpen, setSettingsOpen])

  if (!settingsOpen) return null

  function set(key, val) { setForm(f => ({ ...f, [key]: val })) }

  function handleSave() {
    saveSettings(form)
    setSaved(true)
    setTimeout(() => { setSaved(false); setSettingsOpen(false) }, 800)
  }

  return (
    <>
      <div
        ref={overlayRef}
        className="profile-overlay"
        onClick={e => { if (e.target === overlayRef.current) setSettingsOpen(false) }}
      />
      <div className="profile-drawer">
        <div className="profile-drawer-header">
          <span className="profile-drawer-title">Settings</span>
          <button className="icon-btn" onClick={() => setSettingsOpen(false)} aria-label="Close">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6 6 18M6 6l12 12" strokeLinecap="round"/>
            </svg>
          </button>
        </div>

        <div className="settings-section-label">Notifications</div>
        <Toggle
          checked={form.emailNotifications}
          onChange={v => set('emailNotifications', v)}
          label="Email notifications"
          description="Receive job alert emails (requires SMTP setup)"
        />
        <Toggle
          checked={form.alertSoundEnabled}
          onChange={v => set('alertSoundEnabled', v)}
          label="Alert sound"
          description="Play a sound when new matches arrive"
        />

        <div className="settings-section-label">Search</div>
        <Select
          value={form.defaultResultsLimit}
          onChange={v => set('defaultResultsLimit', v)}
          label="Results per page"
          options={[
            { value: 10, label: '10 results' },
            { value: 20, label: '20 results' },
            { value: 50, label: '50 results' },
          ]}
        />
        <Toggle
          checked={form.autoRefreshAlerts}
          onChange={v => set('autoRefreshAlerts', v)}
          label="Auto-refresh alerts"
          description="Automatically check for new matches every 30 min"
        />

        <div className="profile-actions">
          <button className="btn btn-ghost" onClick={() => setSettingsOpen(false)}>Cancel</button>
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={saved}
          >
            {saved ? '✓ Saved' : 'Save settings'}
          </button>
        </div>
      </div>
    </>
  )
}
