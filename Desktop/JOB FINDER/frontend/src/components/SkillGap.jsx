function SkillGap({ matchingSkills, missingSkills, matchScore }) {
  const total  = matchingSkills.length + missingSkills.length
  const fillColor =
    matchScore >= 90 ? '#10B981' :
    matchScore >= 75 ? '#3B82F6' :
    matchScore >= 60 ? '#F59E0B' : '#EF4444'

  return (
    <div className="skill-gap">
      {/* Match bar */}
      <div className="match-bar-wrap mb-4">
        <div className="match-bar-label">
          <span>Overall Match</span>
          <strong style={{ color: fillColor }}>{matchScore}%</strong>
        </div>
        <div className="match-bar">
          <div
            className="match-bar-fill"
            style={{ width: `${matchScore}%`, background: fillColor }}
          />
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>
          {matchingSkills.length} of {total} required skills matched
        </div>
      </div>

      {/* Matching skills */}
      <div className="skill-gap-row">
        <div className="skill-gap-heading" style={{ color: '#059669' }}>
          <span>✓</span> Skills you have ({matchingSkills.length})
        </div>
        <div className="skill-chips">
          {matchingSkills.map(skill => (
            <span key={skill} className="skill-chip chip-match">
              <span className="chip-icon">✓</span>{skill}
            </span>
          ))}
        </div>
      </div>

      {/* Missing skills */}
      {missingSkills.length > 0 && (
        <div className="skill-gap-row">
          <div className="skill-gap-heading" style={{ color: '#DC2626', marginTop: 16 }}>
            <span>↑</span> Skills to develop ({missingSkills.length})
          </div>
          <div className="skill-chips">
            {missingSkills.map(skill => (
              <span key={skill} className="skill-chip chip-missing">
                <span className="chip-icon">+</span>{skill}
              </span>
            ))}
          </div>
          <p style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 10, lineHeight: 1.6 }}>
            Learning these skills could raise your match score significantly.
          </p>
        </div>
      )}
    </div>
  )
}

export default SkillGap
