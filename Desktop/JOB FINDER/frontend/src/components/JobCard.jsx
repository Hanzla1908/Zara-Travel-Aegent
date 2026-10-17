import { useNavigate } from 'react-router-dom'
import { useApp } from '../App'

function matchColor(score) {
  if (score >= 90) return { color: '#059669', border: '#6EE7B7', bg: '#ECFDF5' }
  if (score >= 75) return { color: '#2563EB', border: '#93C5FD', bg: '#EFF6FF' }
  if (score >= 60) return { color: '#D97706', border: '#FCD34D', bg: '#FFFBEB' }
  return              { color: '#DC2626', border: '#FCA5A5', bg: '#FEF2F2' }
}

const locationTypeClass = { Remote: 'badge-remote', Hybrid: 'badge-hybrid', 'On-site': 'badge-onsite' }
const sourceClass        = { linkedin: 'badge-linkedin', rozee: 'badge-rozee' }
const sourceLabel        = { linkedin: 'LinkedIn', rozee: 'Rozee.pk' }

function JobCard({ job }) {
  const navigate = useNavigate()
  const { savedIds, toggleSaved } = useApp()
  const isSaved = savedIds.has(job.id)
  const mc = matchColor(job.matchScore)

  function handleSave(e) {
    e.stopPropagation()
    toggleSaved(job.id)
  }

  return (
    <div
      className={`job-card${job.applied ? ' applied' : ''}`}
      onClick={() => navigate(`/jobs/${job.id}`)}
    >
      {/* Header */}
      <div className="job-card-header">
        <div className="company-logo" style={{ background: job.color }}>
          {job.initials}
        </div>

        <div className="job-card-title-wrap">
          <div className="job-title">{job.title}</div>
          <div className="job-company">{job.company}</div>
        </div>

        <div
          className="match-badge"
          style={{ color: mc.color, borderColor: mc.border, background: mc.bg }}
        >
          <span className="match-pct">{job.matchScore}%</span>
          <span className="match-label">MATCH</span>
        </div>
      </div>

      {/* Meta */}
      <div className="job-card-meta">
        <span className={`badge ${locationTypeClass[job.locationType] ?? ''}`}>
          {job.locationType}
        </span>
        <span className={`badge ${sourceClass[job.source] ?? ''}`}>
          {sourceLabel[job.source] ?? job.source}
        </span>
        {job.type === 'Contract' && <span className="badge badge-contract">Contract</span>}
        {job.applied && <span className="badge badge-applied">✓ Applied</span>}
        <span className="meta-item" style={{ marginLeft: 'auto' }}>
          <svg className="meta-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"/>
            <circle cx="12" cy="11" r="3"/>
          </svg>
          {job.location}
        </span>
      </div>

      {/* Tags */}
      <div className="job-tags">
        {job.tags.slice(0, 4).map(t => (
          <span key={t} className="tag">{t}</span>
        ))}
      </div>

      {/* Footer */}
      <div className="job-card-footer">
        <div>
          <div className="job-salary">{job.salary}</div>
          <div className="job-posted" style={{ marginTop: 2 }}>
            {job.postedDays === 1 ? 'Posted yesterday' : `Posted ${job.postedDays} days ago`}
          </div>
        </div>
        <div className="card-actions">
          <button
            className="btn btn-outline btn-sm"
            onClick={handleSave}
            style={isSaved ? { borderColor: '#F59E0B', color: '#D97706', background: '#FFFBEB' } : {}}
          >
            {isSaved ? '★ Saved' : '☆ Save'}
          </button>
          <button
            className="btn btn-primary btn-sm"
            onClick={e => { e.stopPropagation(); navigate(`/jobs/${job.id}`) }}
          >
            View
          </button>
        </div>
      </div>
    </div>
  )
}

export default JobCard
