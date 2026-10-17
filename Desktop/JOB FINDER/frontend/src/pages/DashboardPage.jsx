import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApp } from '../App'
import StatCard from '../components/StatCard'
import CVUpload from '../components/CVUpload'
import JobCard from '../components/JobCard'
import { fetchJobs } from '../api/jobs'

const strengthItems = [
  { icon: '📄', label: 'CV Uploaded',          key: 'cv',       ok: false },
  { icon: '🔑', label: 'Skills Extracted',      key: 'skills',   ok: false },
  { icon: '📍', label: 'Preferences Set',       key: 'prefs',    ok: true  },
  { icon: '🔗', label: 'LinkedIn Connected',    key: 'linkedin', ok: false },
  { icon: '🎯', label: 'Job Alerts Configured', key: 'alerts',   ok: false },
]

function DashboardPage() {
  const { savedIds, cvUploaded, cvProfile } = useApp()
  const navigate = useNavigate()

  const [topJobs, setTopJobs]   = useState([])
  const [totalJobs, setTotal]   = useState(0)
  const [allJobs, setAllJobs]   = useState([])
  const [loading, setLoading]   = useState(true)

  const profileStrength = cvProfile?.profile_strength ?? (cvUploaded ? 72 : 0)

  const items = strengthItems.map(it => ({
    ...it,
    ok: it.key === 'cv'     ? cvUploaded
      : it.key === 'skills' ? cvUploaded
      : it.ok,
  }))

  useEffect(() => {
    fetchJobs({ sort: 'match', page_size: 50 })
      .then(data => {
        setTopJobs(data.jobs.slice(0, 3))
        setTotal(data.total)
        setAllJobs(data.jobs)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const linkedinCount = allJobs.filter(j => j.source === 'linkedin').length
  const rozeeCount    = allJobs.filter(j => j.source === 'rozee').length

  return (
    <div>
      {/* Stats */}
      <div className="stat-grid">
        <StatCard
          label="Matched Jobs"
          value={loading ? '…' : totalJobs}
          sub="From all sources"
          icon="🎯"
          color="var(--primary)"
          bg="var(--primary-light)"
        />
        <StatCard
          label="Saved Jobs"
          value={savedIds.size}
          sub="Across all sources"
          icon="🔖"
          color="#D97706"
          bg="#FEF3C7"
        />
        <StatCard
          label="Applied"
          value={0}
          sub="Track via alerts"
          icon="✉️"
          color="var(--success)"
          bg="var(--success-light)"
        />
        <StatCard
          label="Profile Strength"
          value={`${profileStrength}%`}
          sub={cvUploaded ? 'CV analysed' : 'Upload your CV'}
          icon="⚡"
          color="#7C3AED"
          bg="#F5F3FF"
        />
      </div>

      {/* Main grid */}
      <div className="dash-grid">
        {/* Left: top matches */}
        <div>
          <div className="section-header">
            <div className="section-title" style={{ marginBottom: 0 }}>Top Matches for You</div>
            <span className="section-action" onClick={() => navigate('/jobs')}>View all →</span>
          </div>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 32, color: 'var(--text-3)', fontSize: 14 }}>Loading…</div>
          ) : (
            <div className="job-list">
              {topJobs.map(j => <JobCard key={j.id} job={j} />)}
            </div>
          )}
        </div>

        {/* Right column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <CVUpload />

          {/* Profile strength */}
          <div className="card profile-strength-card">
            <div className="profile-strength-header">
              <div>
                <div className="section-title" style={{ marginBottom: 0 }}>Profile Strength</div>
                <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>
                  Complete your profile for better matches
                </div>
              </div>
              <div>
                <div className="strength-score">{profileStrength}%</div>
                <div className="strength-label">
                  {profileStrength >= 80 ? 'Strong' : profileStrength >= 50 ? 'Good' : 'Weak'}
                </div>
              </div>
            </div>

            <div style={{ marginBottom: 14 }}>
              <div style={{ height: 8, background: 'var(--border)', borderRadius: 99, overflow: 'hidden' }}>
                <div style={{
                  height: '100%', width: `${profileStrength}%`,
                  background: 'linear-gradient(90deg, var(--primary), #818CF8)',
                  borderRadius: 99, transition: 'width .4s ease',
                }} />
              </div>
            </div>

            <div className="strength-items">
              {items.map(item => (
                <div key={item.key} className="strength-item">
                  <div
                    className="strength-item-icon"
                    style={{ background: item.ok ? 'var(--success-light)' : 'var(--bg)' }}
                  >
                    {item.icon}
                  </div>
                  <span className="strength-item-label">{item.label}</span>
                  <span
                    className="strength-item-status"
                    style={{ color: item.ok ? 'var(--success)' : 'var(--text-3)' }}
                  >
                    {item.ok ? 'Complete' : 'Missing'}
                  </span>
                </div>
              ))}
            </div>

            <button
              className="btn btn-primary w-full mt-4"
              onClick={() => navigate('/alerts')}
            >
              Configure Alerts →
            </button>
          </div>

          {/* Source breakdown */}
          {!loading && allJobs.length > 0 && (
            <div className="card" style={{ padding: 20 }}>
              <div className="section-title mb-3">Source Breakdown</div>
              {[
                { label: 'LinkedIn',  count: linkedinCount, color: '#2563EB', bg: '#EFF6FF' },
                { label: 'Rozee.pk', count: rozeeCount,    color: '#D97706', bg: '#FFFBEB' },
              ].map(s => (
                <div key={s.label} style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                  <div style={{
                    width: 36, height: 36, borderRadius: 8, background: s.bg,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontWeight: 800, fontSize: 12, color: s.color, flexShrink: 0,
                  }}>
                    {s.label.slice(0, 2).toUpperCase()}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', marginBottom: 4 }}>{s.label}</div>
                    <div style={{ height: 5, background: 'var(--border)', borderRadius: 99, overflow: 'hidden' }}>
                      <div style={{
                        height: '100%',
                        width: `${allJobs.length ? (s.count / allJobs.length) * 100 : 0}%`,
                        background: s.color, borderRadius: 99,
                      }} />
                    </div>
                  </div>
                  <span style={{ fontSize: 14, fontWeight: 700, color: s.color }}>{s.count}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default DashboardPage
