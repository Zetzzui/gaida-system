import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { useCallback } from 'react'

import PortalSelection from './features/auth/PortalSelection'
import StudentLogin from './features/student/StudentLogin'
import CounselorLogin from './features/auth/CounselorLogin'
import InformedConsent from './features/auth/InformedConsent'
import StudentDashboard from './features/student/StudentDashboard'
import CounselorDashboard from './features/counselor/CounselorDashboard'
import ForgotPassword from './features/auth/ForgotPassword'
import PWABanner from './components/PWABanner'
import ResearchFlow from './features/research/ResearchFlow'
import ResearchSUS from './features/research/ResearchSUS'
import Withdraw from './features/research/Withdraw'

// ─────────────────────────────────────────────────────────────
// When a queued message finally gets a real GPT response after
// reconnecting, this handler fires. You can emit a custom event
// that StudentDashboard (or your chat component) listens to,
// so the real GAIDA reply replaces the offline placeholder.
// ─────────────────────────────────────────────────────────────
const QUEUE_SYNCED_EVENT = 'gaida:queue-synced'

function App() {

  const handleQueuedMessageSent = useCallback((data) => {
    // data = { original: { message, intent, ... }, response: { response, ... } }
    // Dispatch a custom event so any mounted chat component can pick it up
    window.dispatchEvent(
      new CustomEvent(QUEUE_SYNCED_EVENT, { detail: data })
    )
  }, [])

  return (
    <BrowserRouter>

      {/* PWA Banner — fixed top, visible on all routes */}
      <PWABanner onQueuedMessageSent={handleQueuedMessageSent} />

      <Routes>
        <Route path="/"                    element={<PortalSelection />} />
        <Route path="/student-login"       element={<StudentLogin />} />
        <Route path="/counselor-login"     element={<CounselorLogin />} />
        <Route path="/forgot-password"     element={<ForgotPassword />} />
        <Route path="/consent"             element={<InformedConsent />} />
        <Route path="/student-dashboard"   element={<StudentDashboard />} />
        <Route path="/counselor-dashboard" element={<CounselorDashboard />} />
        <Route path="/research"            element={<ResearchFlow />} />
        <Route path="/research-sus"        element={<ResearchSUS />} />
        <Route path="/research/withdraw"   element={<Withdraw />} />
      </Routes>

    </BrowserRouter>
  )
}

export default App