import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useState, createContext, useContext, useEffect } from 'react'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import ProfileModal from './components/ProfileModal'
import DashboardPage from './pages/DashboardPage'
import JobsPage from './pages/JobsPage'
import JobDetailPage from './pages/JobDetailPage'
import SavedJobsPage from './pages/SavedJobsPage'
import AlertsPage from './pages/AlertsPage'
import { fetchSavedIds, saveJob, unsaveJob } from './api/saved'

export const AppCtx = createContext(null)
export const useApp = () => useContext(AppCtx)

const _PROFILE_KEY = 'jf_profile'
const _DEFAULT_PROFILE = { name: 'Hanzla Arif', email: 'hanzla90@gmail.com', location: '' }

function _loadProfile() {
  try { return JSON.parse(localStorage.getItem(_PROFILE_KEY)) || _DEFAULT_PROFILE }
  catch { return _DEFAULT_PROFILE }
}

function Layout({ children }) {
  return (
    <div className="app">
      <Sidebar />
      <div className="main-content">
        <TopBar />
        <main className="page-content">{children}</main>
      </div>
      <ProfileModal />
    </div>
  )
}

function App() {
  const [savedIds, setSavedIds]         = useState(new Set())
  const [cvUploaded, setCvUploaded]     = useState(false)
  const [cvFile, setCvFile]             = useState(null)
  const [cvProfile, setCvProfile]       = useState(null)
  const [userProfile, setUserProfile]   = useState(_loadProfile)
  const [profileOpen, setProfileOpen]   = useState(false)

  function saveUserProfile(p) {
    setUserProfile(p)
    try { localStorage.setItem(_PROFILE_KEY, JSON.stringify(p)) } catch {}
  }

  useEffect(() => {
    fetchSavedIds().then(setSavedIds).catch(() => {})
  }, [])

  async function toggleSaved(id) {
    const wasSaved = savedIds.has(id)
    // Optimistic update
    setSavedIds(prev => {
      const next = new Set(prev)
      wasSaved ? next.delete(id) : next.add(id)
      return next
    })
    try {
      if (wasSaved) await unsaveJob(id)
      else await saveJob(id)
    } catch {
      // Revert
      setSavedIds(prev => {
        const next = new Set(prev)
        wasSaved ? next.add(id) : next.delete(id)
        return next
      })
    }
  }

  return (
    <AppCtx.Provider value={{
      savedIds, toggleSaved,
      cvUploaded, setCvUploaded, cvFile, setCvFile, cvProfile, setCvProfile,
      userProfile, saveUserProfile,
      profileOpen, setProfileOpen,
    }}>
      <BrowserRouter>
        <Layout>
          <Routes>
            <Route path="/"         element={<DashboardPage />} />
            <Route path="/jobs"     element={<JobsPage />} />
            <Route path="/jobs/:id" element={<JobDetailPage />} />
            <Route path="/saved"    element={<SavedJobsPage />} />
            <Route path="/alerts"   element={<AlertsPage />} />
            <Route path="*"         element={<Navigate to="/" replace />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </AppCtx.Provider>
  )
}

export default App
