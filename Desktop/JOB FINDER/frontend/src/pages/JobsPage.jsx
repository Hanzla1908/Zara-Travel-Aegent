import { useState, useEffect } from 'react'
import JobCard from '../components/JobCard'
import SearchFilters from '../components/SearchFilters'
import { fetchJobs } from '../api/jobs'

const defaultFilters = {
  keyword:    '',
  location:   '',
  experience: [],
  type:       'Any',
  sources:    ['linkedin', 'rozee'],
  sort:       'match',
}

function Spinner() {
  return (
    <div style={{ textAlign: 'center', padding: 48, color: 'var(--text-3)' }}>
      <div style={{ fontSize: 32, marginBottom: 10, animation: 'spin 1s linear infinite', display: 'inline-block' }}>⏳</div>
      <div style={{ fontSize: 14 }}>Loading jobs…</div>
    </div>
  )
}

function JobsPage() {
  const [filters, setFilters] = useState(defaultFilters)
  const [result, setResult]   = useState({ jobs: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)

    const params = {
      sort:      filters.sort,
      source:    filters.sources,
      page_size: 50,
    }
    if (filters.keyword)          params.keyword    = filters.keyword
    if (filters.location)         params.location   = filters.location
    if (filters.experience.length) params.experience = filters.experience
    if (filters.type !== 'Any')   params.type       = filters.type

    const timer = setTimeout(() => {
      fetchJobs(params)
        .then(data => { setResult(data); setLoading(false) })
        .catch(() => { setError('Could not reach the backend.'); setLoading(false) })
    }, 350)

    return () => clearTimeout(timer)
  }, [filters])

  return (
    <div>
      {/* Top bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ fontSize: 14, color: 'var(--text-2)' }}>
          {loading
            ? <span>Searching…</span>
            : error
              ? <span style={{ color: '#DC2626' }}>Error loading jobs</span>
              : <><strong style={{ color: 'var(--text-1)' }}>{result.total}</strong> jobs found</>
          }
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {['match', 'date'].map(s => (
            <button
              key={s}
              className={`btn btn-sm ${filters.sort === s ? 'btn-primary' : 'btn-outline'}`}
              onClick={() => setFilters(f => ({ ...f, sort: s }))}
            >
              {s === 'match' ? '🎯 Best Match' : '🕐 Newest'}
            </button>
          ))}
        </div>
      </div>

      <div className="jobs-layout">
        <SearchFilters filters={filters} onChange={setFilters} />

        <div>
          {loading ? (
            <Spinner />
          ) : error ? (
            <div className="card" style={{ padding: 48, textAlign: 'center' }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>⚠️</div>
              <div style={{ fontWeight: 700, marginBottom: 8, color: 'var(--text-1)', fontSize: 16 }}>
                Backend not reachable
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 20 }}>
                Make sure the FastAPI server is running on port 8000.
              </div>
              <button className="btn btn-primary" onClick={() => setFilters(f => ({ ...f }))}>
                Retry
              </button>
            </div>
          ) : result.jobs.length === 0 ? (
            <div className="card" style={{ padding: 48, textAlign: 'center', color: 'var(--text-3)' }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>🔍</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-2)', marginBottom: 6 }}>No jobs found</div>
              <div style={{ fontSize: 14 }}>Try adjusting your filters or search keyword.</div>
            </div>
          ) : (
            <div className="job-list">
              {result.jobs.map(j => <JobCard key={j.id} job={j} />)}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default JobsPage
