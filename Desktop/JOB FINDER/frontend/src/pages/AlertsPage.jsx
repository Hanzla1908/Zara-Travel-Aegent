import { useState, useEffect } from 'react'
import { fetchAlerts, createAlert, updateAlert, deleteAlert } from '../api/alerts'

const sourceLabel = { linkedin: 'LinkedIn', rozee: 'Rozee.pk' }

function Toggle({ on, onChange }) {
  return (
    <div className={`toggle${on ? ' on' : ''}`} onClick={onChange}>
      <div className="toggle-knob" />
    </div>
  )
}

const emptyForm = {
  name: '', keywords: '', location: '',
  frequency: 'Daily', sources: ['linkedin', 'rozee'],
}

function AlertsPage() {
  const [alerts, setAlerts]   = useState([])
  const [loading, setLoading] = useState(true)
  const [form, setForm]       = useState(emptyForm)
  const [saving, setSaving]   = useState(false)
  const [flash, setFlash]     = useState(null)   // { type: 'success'|'error', msg }

  useEffect(() => {
    fetchAlerts()
      .then(data => { setAlerts(data); setLoading(false) })
      .catch(() => { setLoading(false) })
  }, [])

  function showFlash(type, msg) {
    setFlash({ type, msg })
    setTimeout(() => setFlash(null), 3000)
  }

  async function handleToggle(id) {
    const alert = alerts.find(a => a.id === id)
    const patch = { active: !alert.active }
    setAlerts(prev => prev.map(a => a.id === id ? { ...a, ...patch } : a))
    try {
      await updateAlert(id, patch)
    } catch {
      setAlerts(prev => prev.map(a => a.id === id ? { ...a, active: alert.active } : a))
    }
  }

  async function handleDelete(id) {
    setAlerts(prev => prev.filter(a => a.id !== id))
    try {
      await deleteAlert(id)
    } catch {
      showFlash('error', 'Failed to delete alert.')
    }
  }

  function toggleSource(src) {
    setForm(f => ({
      ...f,
      sources: f.sources.includes(src)
        ? f.sources.filter(s => s !== src)
        : [...f.sources, src],
    }))
  }

  async function handleSave(e) {
    e.preventDefault()
    if (!form.name.trim() || !form.keywords.trim()) return
    setSaving(true)
    try {
      const created = await createAlert({
        name:      form.name.trim(),
        keywords:  form.keywords.trim(),
        location:  form.location.trim(),
        frequency: form.frequency,
        sources:   form.sources,
      })
      setAlerts(prev => [created, ...prev])
      setForm(emptyForm)
      showFlash('success', 'Alert created!')
    } catch {
      showFlash('error', 'Failed to create alert.')
    } finally {
      setSaving(false)
    }
  }

  function formatDate(iso) {
    if (!iso) return ''
    return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
  }

  return (
    <div>
      <div className="alerts-layout">
        {/* Alert list */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <div style={{ fontSize: 14, color: 'var(--text-2)' }}>
              <strong style={{ color: 'var(--text-1)' }}>{alerts.length}</strong> alerts configured
            </div>
            <span className={`badge ${alerts.some(a => a.active) ? 'badge-applied' : ''}`}>
              {alerts.filter(a => a.active).length} active
            </span>
          </div>

          {loading ? (
            <div style={{ textAlign: 'center', padding: 48, color: 'var(--text-3)', fontSize: 14 }}>
              Loading alerts…
            </div>
          ) : alerts.length === 0 ? (
            <div className="card" style={{ padding: 48, textAlign: 'center', color: 'var(--text-3)' }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>🔔</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-2)', marginBottom: 6 }}>No alerts yet</div>
              <div style={{ fontSize: 14 }}>Create your first alert using the form →</div>
            </div>
          ) : (
            <div className="alert-list">
              {alerts.map(alert => (
                <div key={alert.id} className="card alert-card">
                  <div className="alert-card-header">
                    <div>
                      <div className="alert-name">{alert.name}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>
                        Created {formatDate(alert.created_at)}
                      </div>
                    </div>
                    <Toggle on={alert.active} onChange={() => handleToggle(alert.id)} />
                  </div>

                  <div className="alert-meta">
                    <span className="alert-meta-item">🔑 {alert.keywords}</span>
                    {alert.location && <span className="alert-meta-item">📍 {alert.location}</span>}
                    <span className="alert-meta-item">🔁 {alert.frequency}</span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div className="alert-sources">
                      {(alert.sources ?? []).map(s => (
                        <span key={s} className={`badge badge-${s}`}>{sourceLabel[s] ?? s}</span>
                      ))}
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button
                        className="btn btn-danger btn-sm"
                        style={{ fontSize: 12 }}
                        onClick={() => handleDelete(alert.id)}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Create alert form */}
        <div className="card alert-form-card">
          <h3>Create New Alert</h3>

          {flash && (
            <div style={{
              background: flash.type === 'success' ? 'var(--success-light)' : '#FEF2F2',
              border: `1px solid ${flash.type === 'success' ? '#6EE7B7' : '#FCA5A5'}`,
              borderRadius: 'var(--r)', padding: '10px 14px', marginBottom: 16,
              fontSize: 13, color: flash.type === 'success' ? '#065F46' : '#991B1B', fontWeight: 600,
            }}>
              {flash.type === 'success' ? '✓ ' : '✕ '}{flash.msg}
            </div>
          )}

          <form onSubmit={handleSave}>
            <div className="form-group">
              <label className="form-label">Alert Name *</label>
              <input
                className="form-input"
                placeholder="e.g. React Jobs in Lahore"
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">Keywords *</label>
              <input
                className="form-input"
                placeholder="e.g. React, TypeScript, Frontend"
                value={form.keywords}
                onChange={e => setForm(f => ({ ...f, keywords: e.target.value }))}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">Location</label>
              <input
                className="form-input"
                placeholder="City or Remote"
                value={form.location}
                onChange={e => setForm(f => ({ ...f, location: e.target.value }))}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Frequency</label>
              <select
                className="form-input"
                value={form.frequency}
                onChange={e => setForm(f => ({ ...f, frequency: e.target.value }))}
                style={{ cursor: 'pointer' }}
              >
                <option>Instantly</option>
                <option>Daily</option>
                <option>Weekly</option>
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Job Sources</label>
              <div className="form-source-row">
                {['linkedin', 'rozee'].map(src => (
                  <button
                    key={src}
                    type="button"
                    className={`source-toggle-btn${form.sources.includes(src) ? ' active' : ''}`}
                    onClick={() => toggleSource(src)}
                  >
                    {sourceLabel[src]}
                  </button>
                ))}
              </div>
            </div>

            <button type="submit" className="btn btn-primary w-full" style={{ marginTop: 8 }} disabled={saving}>
              {saving ? 'Creating…' : '🔔 Create Alert'}
            </button>
          </form>

          <div style={{ marginTop: 20, padding: 16, background: 'var(--bg)', borderRadius: 'var(--r)', fontSize: 12, color: 'var(--text-3)', lineHeight: 1.6 }}>
            <strong style={{ color: 'var(--text-2)' }}>💡 Tips</strong><br />
            Use commas to separate keywords. Be specific — "React, Senior, Remote" works better than just "Developer".
          </div>
        </div>
      </div>
    </div>
  )
}

export default AlertsPage
