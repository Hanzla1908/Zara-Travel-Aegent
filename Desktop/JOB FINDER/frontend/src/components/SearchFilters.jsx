import { useState } from 'react'

const experienceLevels = ['Any', 'Junior', 'Mid', 'Senior', 'Lead']
const jobTypes = ['Any', 'Full-time', 'Part-time', 'Contract', 'Remote']

function SearchFilters({ filters, onChange }) {
  function set(key, val) {
    onChange({ ...filters, [key]: val })
  }

  function toggleSource(src) {
    const current = filters.sources
    const updated = current.includes(src)
      ? current.filter(s => s !== src)
      : [...current, src]
    set('sources', updated)
  }

  function toggleJobType(type) {
    set('type', filters.type === type ? 'Any' : type)
  }

  return (
    <div className="filters-panel">
      <div className="filter-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ display:'inline', marginRight:6, verticalAlign:'middle' }}>
          <path d="M3 4h18M7 12h10M11 20h2" strokeLinecap="round"/>
        </svg>
        Filters
      </div>

      {/* Keyword */}
      <div className="filter-section">
        <div className="filter-label">Keyword</div>
        <input
          className="filter-input"
          placeholder="e.g. React, Python…"
          value={filters.keyword}
          onChange={e => set('keyword', e.target.value)}
        />
      </div>

      {/* Location */}
      <div className="filter-section">
        <div className="filter-label">Location</div>
        <input
          className="filter-input"
          placeholder="City or Remote"
          value={filters.location}
          onChange={e => set('location', e.target.value)}
        />
      </div>

      <div className="filter-divider" />

      {/* Experience */}
      <div className="filter-section">
        <div className="filter-label">Experience</div>
        <div className="checkbox-group">
          {experienceLevels.filter(l => l !== 'Any').map(level => (
            <label key={level} className="checkbox-item">
              <input
                type="checkbox"
                checked={filters.experience.includes(level)}
                onChange={() => {
                  const curr = filters.experience
                  set('experience', curr.includes(level)
                    ? curr.filter(e => e !== level)
                    : [...curr, level])
                }}
              />
              {level}
            </label>
          ))}
        </div>
      </div>

      <div className="filter-divider" />

      {/* Job Type */}
      <div className="filter-section">
        <div className="filter-label">Job Type</div>
        <div className="checkbox-group">
          {jobTypes.filter(t => t !== 'Any').map(type => (
            <label key={type} className="checkbox-item">
              <input
                type="checkbox"
                checked={filters.type === type}
                onChange={() => toggleJobType(type)}
              />
              {type}
            </label>
          ))}
        </div>
      </div>

      <div className="filter-divider" />

      {/* Source */}
      <div className="filter-section">
        <div className="filter-label">Job Source</div>
        <button
          className={`source-btn${filters.sources.includes('linkedin') ? ' active-linkedin' : ''}`}
          onClick={() => toggleSource('linkedin')}
        >
          <span className="source-dot" style={{ background: '#2563EB' }} />
          LinkedIn
          {filters.sources.includes('linkedin') && <span style={{ marginLeft:'auto', fontSize:14 }}>✓</span>}
        </button>
        <button
          className={`source-btn${filters.sources.includes('rozee') ? ' active-rozee' : ''}`}
          onClick={() => toggleSource('rozee')}
        >
          <span className="source-dot" style={{ background: '#F59E0B' }} />
          Rozee.pk
          {filters.sources.includes('rozee') && <span style={{ marginLeft:'auto', fontSize:14 }}>✓</span>}
        </button>
      </div>

      <div className="filter-divider" />

      {/* Sort */}
      <div className="filter-section">
        <div className="filter-label">Sort by</div>
        <select
          className="filter-select"
          value={filters.sort}
          onChange={e => set('sort', e.target.value)}
        >
          <option value="match">Best Match</option>
          <option value="date">Most Recent</option>
          <option value="salary">Highest Salary</option>
        </select>
      </div>

      <div className="filter-actions">
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => onChange({ keyword: '', location: '', experience: [], type: 'Any', sources: ['linkedin', 'rozee'], sort: 'match' })}
          style={{ flex: 1 }}
        >
          Clear
        </button>
        <button className="btn btn-primary btn-sm" style={{ flex: 2 }}>
          Apply
        </button>
      </div>
    </div>
  )
}

export default SearchFilters
