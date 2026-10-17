import { useRef, useState } from 'react'
import { useApp } from '../App'
import { uploadCV } from '../api/cv'

function CVUpload() {
  const { cvUploaded, setCvUploaded, cvFile, setCvFile, cvProfile, setCvProfile } = useApp()
  const [dragging, setDragging] = useState(false)
  const [progress, setProgress] = useState(0)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError]       = useState(null)
  const inputRef = useRef(null)

  async function handleFile(file) {
    if (!file) return
    setCvFile(file.name)
    setAnalyzing(true)
    setProgress(0)
    setError(null)

    // Animate progress bar while upload happens
    let p = 0
    const interval = setInterval(() => {
      p += Math.random() * 12
      if (p < 90) setProgress(Math.round(p))
    }, 150)

    try {
      const result = await uploadCV(file)
      clearInterval(interval)
      setProgress(100)
      setCvProfile(result.profile)
      setTimeout(() => { setAnalyzing(false); setCvUploaded(true) }, 400)
    } catch (err) {
      clearInterval(interval)
      setAnalyzing(false)
      setProgress(0)
      setCvFile(null)
      const msg = err?.response?.data?.detail ?? 'Upload failed. Check file type (PDF/DOCX) and size (max 10 MB).'
      setError(msg)
    }
  }

  function onDrop(e) {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  const strength = cvProfile?.profile_strength ?? 72

  if (cvUploaded) {
    const skills = cvProfile?.skills ?? []
    return (
      <div className="card cv-upload-card">
        <div className="section-header mb-3">
          <div className="section-title" style={{ marginBottom: 0 }}>CV / Resume</div>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => { setCvUploaded(false); setCvFile(null); setCvProfile(null) }}
          >
            Replace
          </button>
        </div>
        <div className="cv-uploaded-state">
          <span className="cv-check">✅</span>
          <div>
            <div className="cv-file-name">{cvFile}</div>
            <div className="cv-file-sub">
              Analysed · {skills.length} skills detected · Profile strength {strength}%
            </div>
          </div>
        </div>
        <div className="cv-progress" style={{ marginTop: 16 }}>
          <div className="cv-progress-label">
            <span>Profile Strength</span>
            <span style={{ fontWeight: 700, color: 'var(--primary)' }}>{strength}%</span>
          </div>
          <div className="cv-progress-bar">
            <div className="cv-progress-fill" style={{ width: `${strength}%` }} />
          </div>
        </div>
        {skills.length > 0 && (
          <div style={{ marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {skills.slice(0, 8).map(s => (
              <span key={s} style={{
                padding: '2px 8px', borderRadius: 99, fontSize: 11, fontWeight: 600,
                background: 'var(--primary-light)', color: 'var(--primary)',
              }}>{s}</span>
            ))}
            {skills.length > 8 && (
              <span style={{ fontSize: 11, color: 'var(--text-3)', alignSelf: 'center' }}>
                +{skills.length - 8} more
              </span>
            )}
          </div>
        )}
      </div>
    )
  }

  if (analyzing) {
    return (
      <div className="card cv-upload-card">
        <div className="section-title mb-3">CV / Resume</div>
        <div className="cv-progress" style={{ padding: '12px 0' }}>
          <div className="cv-progress-label">
            <span>Analysing <strong>{cvFile}</strong>…</span>
            <span style={{ fontWeight: 700, color: 'var(--primary)' }}>{progress}%</span>
          </div>
          <div className="cv-progress-bar">
            <div className="cv-progress-fill" style={{ width: `${progress}%` }} />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="card cv-upload-card">
      <div className="section-title mb-3">CV / Resume</div>

      {error && (
        <div style={{
          background: '#FEF2F2', border: '1px solid #FCA5A5', borderRadius: 'var(--r)',
          padding: '8px 12px', marginBottom: 12, fontSize: 12, color: '#991B1B',
        }}>
          {error}
        </div>
      )}

      <div
        className={`cv-dropzone${dragging ? ' dragging' : ''}`}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
      >
        <div className="cv-icon">📄</div>
        <h3>Drop your CV here</h3>
        <p>or <span className="cv-link">browse files</span></p>
        <div className="cv-formats">
          {['PDF', 'DOCX'].map(f => (
            <span key={f} className="cv-format-badge">{f}</span>
          ))}
        </div>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx"
        style={{ display: 'none' }}
        onChange={e => handleFile(e.target.files?.[0])}
      />
    </div>
  )
}

export default CVUpload
