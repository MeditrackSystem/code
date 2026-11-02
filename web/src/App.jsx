import { HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { supabase } from './supabaseClient'
import Login from './pages/Login'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Patients from './pages/Patients'
import PatientDetail from './pages/PatientDetail'
import Users from './pages/Users'
import ScanLogs from './pages/ScanLogs'
import AuditLogs from './pages/AuditLogs'
import RFIDTags from './pages/RFIDTags'
import { getSession, setSession, clearSession } from './session'

export default function App() {
  const [user, setUser] = useState(getSession())

  useEffect(() => {
    const onStorage = () => setUser(getSession())
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  function login(u) { setSession(u); setUser(u) }
  function logout() { clearSession(); setUser(null) }

  return (
    <HashRouter>
      <Routes>
        <Route path="/login" element={user ? <Navigate to="/" /> : <Login onLogin={login} />} />
        <Route path="/" element={user ? <Layout user={user} onLogout={logout} /> : <Navigate to="/login" />}>
          <Route index element={<Dashboard />} />
          <Route path="patients" element={<Patients />} />
          <Route path="patients/:id" element={<PatientDetail />} />
          <Route path="rfid" element={<RFIDTags />} />
          <Route path="scans" element={<ScanLogs />} />
          <Route path="audit" element={<AuditLogs />} />
          <Route path="users" element={user?.role === 'Administrator' ? <Users /> : <Navigate to="/" />} />
        </Route>
      </Routes>
    </HashRouter>
  )
}
