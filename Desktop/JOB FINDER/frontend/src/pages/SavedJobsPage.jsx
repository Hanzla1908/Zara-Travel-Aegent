import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApp } from '../App'
import JobCard from '../components/JobCard'
import { fetchSavedJobs } from '../api/saved'

function SavedJobsPage() {
  const { savedIds } = useApp()
  const navigate = useNavigate()
  const [jobs, setJobs]     = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState(null)

  useEffect(() => {
    setLoading(true)
    fetchSavedJobs()
      .then(data => { setJobs(data); setLoading(false) })
      .catch(() => { setError('Could not load saved jobs.'); setLoading(false) })
  }, [savedIds])  // refetch whenever savedIds changes

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 64, color: 'var(--text-3)', fontSize: 14 }}>
        Loading saved jobs…
      </div>
    )
  }

  if (error) {
    return (
      <div className="card" style={{ padding: 48, textAlign: 'center' }}>
        <div style={{ fontSize: 40, marginBottom: 12 }}>⚠️</div>
        <div style={{ fontWeight: 700, marginBottom: 8 }}>{error}</div>
        <button className="btn btn-primary" onClick={() => setLoading(true)}>Retry</button>
      </div>
    )
  }

  if (jobs.length === 0) {
    return (
      <div className="card saved-empty">
        <div className="saved-empty-icon">🔖</div>
        <h3>No saved jobs yet</h3>
        <p style={{ fontSize: 14 }}>Tap the Save button on any job card to bookmark it here.</p>
        <button className="btn btn-primary mt-4" onClick={() => navigate('/jobs')}>
          Browse Jobs
        </button>
      </div>
    )
  }

  const applied = jobs.filter(j => j.applied)
  const pending = jobs.filter(j => !j.applied)
  const avgMatch = Math.round(jobs.reduce((s, j) => s + j.matchScore, 0) / jobs.length)

  return (
    <div>
      {/* Summary strip */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap' }}>
        {[
          { label: 'Total Saved', value: jobs.length,    color: 'var(--primary)', bg: 'var(--primary-light)' },
          { label: 'Applied',     value: applied.length, color: 'var(--success)', bg: 'var(--success-light)'  },
          { label: 'Pending',     value: pending.length, color: '#D97706',        bg: '#FFFBEB'               },
          { label: 'Avg Match',   value: `${avgMatch}%`, color: '#7C3AED',        bg: '#F5F3FF'               },
        ].map(s => (
          <div key={s.label} className="card" style={{ padding: '14px 20px', display: 'flex', alignItems: 'center', gap: 12, flex: 1, minWidth: 140 }}>
            <div style={{ width: 38, height: 38, borderRadius: 8, background: s.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 16, color: s.color }}>
              {s.value}
            </div>
            <span style={{ fontSize: 13, color: 'var(--text-2)', fontWeight: 500 }}>{s.label}</span>
          </div>
        ))}
      </div>

      {/* Applied */}
      {applied.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <div className="section-header">
            <div className="section-title" style={{ marginBottom: 0 }}>Applied Jobs</div>
            <span className="badge badge-applied">{applied.length} applied</span>
          </div>
          <div className="job-list">
            {applied.map(j => <JobCard key={j.id} job={j} />)}
          </div>
        </div>
      )}

      {/* Pending */}
      {pending.length > 0 && (
        <div>
          <div className="section-header">
            <div className="section-title" style={{ marginBottom: 0 }}>Saved — Not Yet Applied</div>
            <span className="badge" style={{ background: 'var(--warning-light)', color: '#92400E' }}>
              {pending.length} pending
            </span>
          </div>
          <div className="job-list">
            {pending.map(j => <JobCard key={j.id} job={j} />)}
          </div>
        </div>
      )}
    </div>
  )
}

export default SavedJobsPage
