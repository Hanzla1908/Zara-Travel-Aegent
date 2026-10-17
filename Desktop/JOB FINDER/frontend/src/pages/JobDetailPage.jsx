import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useApp } from '../App'
import SkillGap from '../components/SkillGap'
import { fetchJob, fetchJobs } from '../api/jobs'

const locationTypeClass = { Remote: 'badge-remote', Hybrid: 'badge-hybrid', 'On-site': 'badge-onsite' }
const sourceLabel        = { linkedin: 'LinkedIn', rozee: 'Rozee.pk' }

function JobDetailPage() {
  const { id }   = useParams()
  const navigate = useNavigate()
  const { savedIds, toggleSaved } = useApp()

  const [job, setJob]             = useState(null)
  const [similar, setSimilar]     = useState([])
  const [loading, setLoading]     = useState(true)
  const [notFound, setNotFound]   = useState(false)

  const isSaved = job ? savedIds.has(job.id) : false

  useEffect(() => {
    setLoading(true)
    setNotFound(false)
    Promise.all([
      fetchJob(id),
      fetchJobs({ sort: 'match', page_size: 10 }),
    ])
      .then(([jobData, listData]) => {
        setJob(jobData)
        setSimilar(listData.jobs.filter(j => j.id !== jobData.id).slice(0, 3))
        setLoading(false)
      })
      .catch(err => {
        if (err?.response?.status === 404) setNotFound(true)
        setLoading(false)
      })
  }, [id])

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 64, color: 'var(--text-3)', fontSize: 14 }}>
        Loading job…
      </div>
    )
  }

  if (notFound || !job) {
    return (
      <div className="card" style={{ padding: 48, textAlign: 'center' }}>
        <div style={{ fontSize: 40, marginBottom: 12 }}>😕</div>
        <div style={{ fontWeight: 700, marginBottom: 12, fontSize: 18 }}>Job not found</div>
        <button className="btn btn-primary" onClick={() => navigate('/jobs')}>Back to Jobs</button>
      </div>
    )
  }

  const matchBorderColor = job.matchScore >= 90 ? '#10B981' : job.matchScore >= 75 ? '#3B82F6' : '#F59E0B'
  const matchTextColor   = job.matchScore >= 90 ? '#059669' : job.matchScore >= 75 ? '#1D4ED8' : '#D97706'

  return (
    <div>
      {/* Breadcrumb */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20, fontSize: 13, color: 'var(--text-3)' }}>
        <span style={{ cursor: 'pointer', color: 'var(--primary)' }} onClick={() => navigate('/jobs')}>
          Find Jobs
        </span>
        <span>›</span>
        <span style={{ color: 'var(--text-2)' }}>{job.title}</span>
      </div>

      <div className="job-detail-layout">
        {/* Main */}
        <div className="job-detail-main">
          <div className="card jd-card">
            {/* Header */}
            <div className="jd-header">
              <div className="jd-logo" style={{ background: job.color }}>{job.initials}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="jd-title">{job.title}</div>
                <div className="jd-company">{job.company} · {job.location}</div>
              </div>
              <div style={{ textAlign: 'center', flexShrink: 0 }}>
                <div style={{
                  width: 72, height: 72, borderRadius: '50%',
                  border: `4px solid ${matchBorderColor}`,
                  display: 'flex', flexDirection: 'column',
                  alignItems: 'center', justifyContent: 'center',
                  color: matchTextColor,
                }}>
                  <span style={{ fontSize: 22, fontWeight: 800, lineHeight: 1 }}>{job.matchScore}%</span>
                  <span style={{ fontSize: 9, letterSpacing: .5, opacity: .7 }}>MATCH</span>
                </div>
              </div>
            </div>

            {/* Meta badges */}
            <div className="jd-meta">
              <span className={`badge ${locationTypeClass[job.locationType] ?? ''}`}>{job.locationType}</span>
              <span className={`badge ${job.type === 'Full-time' ? 'badge-fulltime' : 'badge-contract'}`}>{job.type}</span>
              <span className="badge" style={{ background: '#F1F5F9', color: 'var(--text-2)' }}>{job.experience}</span>
              <span className="badge badge-linkedin">{sourceLabel[job.source] ?? job.source}</span>
              {job.applied && <span className="badge badge-applied">✓ Applied</span>}
              <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-3)' }}>
                {job.postedDays === 1 ? 'Posted yesterday' : `Posted ${job.postedDays} days ago`}
              </span>
            </div>

            {/* Salary */}
            {job.salary && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '12px 0', borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)', marginBottom: 4 }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--text-3)" strokeWidth="2">
                  <line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/>
                </svg>
                <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-1)' }}>{job.salary}</span>
                <span style={{ fontSize: 12, color: 'var(--text-3)' }}>· {job.experience}</span>
              </div>
            )}

            {/* Description */}
            {job.description && (
              <>
                <div className="jd-section-title">About the Role</div>
                <p className="jd-description">{job.description}</p>
              </>
            )}

            {/* Requirements */}
            {job.requirements.length > 0 && (
              <>
                <div className="jd-section-title">Requirements</div>
                <div className="jd-requirements">
                  {job.requirements.map((req, i) => (
                    <div key={i} className="jd-req-item">
                      <div className="jd-req-dot" />
                      <span>{req}</span>
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* Tags */}
            {job.tags.length > 0 && (
              <>
                <div className="jd-section-title">Skills & Technologies</div>
                <div className="job-tags">
                  {job.tags.map(t => <span key={t} className="tag">{t}</span>)}
                </div>
              </>
            )}

            {/* Actions */}
            <div className="jd-actions">
              <button className="btn btn-primary" style={{ flex: 2 }}>Apply Now</button>
              <button
                className="btn btn-outline"
                style={isSaved ? { borderColor: '#F59E0B', color: '#D97706', background: '#FFFBEB' } : {}}
                onClick={() => toggleSaved(job.id)}
              >
                {isSaved ? '★ Saved' : '☆ Save'}
              </button>
              <button className="btn btn-outline btn-icon" title="Share">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
                  <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
                </svg>
              </button>
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <div className="job-detail-sidebar">
          {/* Skill Gap */}
          <div className="card" style={{ padding: 24 }}>
            <div className="section-title mb-3">Skill Gap Analysis</div>
            <SkillGap
              matchingSkills={job.matchingSkills}
              missingSkills={job.missingSkills}
              matchScore={job.matchScore}
            />
            {job.missingSkills.length > 0 && (
              <button className="btn btn-outline w-full mt-4" style={{ fontSize: 13 }}>
                📚 Find Courses for Missing Skills
              </button>
            )}
          </div>

          {/* Company info */}
          <div className="card" style={{ padding: 24 }}>
            <div className="section-title mb-3">About {job.company}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
              <div style={{ width: 46, height: 46, borderRadius: 10, background: job.color, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 16, color: '#fff' }}>
                {job.initials}
              </div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 14 }}>{job.company}</div>
                <div style={{ fontSize: 12, color: 'var(--text-3)' }}>Technology · Pakistan</div>
              </div>
            </div>
          </div>

          {/* Similar jobs */}
          {similar.length > 0 && (
            <div className="card" style={{ padding: 24 }}>
              <div className="section-header" style={{ marginBottom: 12 }}>
                <div className="section-title" style={{ marginBottom: 0 }}>Similar Jobs</div>
                <span className="section-action" onClick={() => navigate('/jobs')}>View all</span>
              </div>
              {similar.map(j => (
                <div
                  key={j.id}
                  style={{ display: 'flex', gap: 10, padding: '10px 0', borderBottom: '1px solid var(--border)', cursor: 'pointer' }}
                  onClick={() => navigate(`/jobs/${j.id}`)}
                >
                  <div style={{ width: 34, height: 34, borderRadius: 7, background: j.color, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 11, color: '#fff', flexShrink: 0 }}>
                    {j.initials}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', marginBottom: 1 }}>{j.title}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{j.company}</div>
                  </div>
                  <div style={{ fontSize: 12, fontWeight: 800, flexShrink: 0, color: j.matchScore >= 90 ? '#059669' : j.matchScore >= 75 ? '#2563EB' : '#D97706' }}>
                    {j.matchScore}%
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default JobDetailPage
