import { useState } from 'react'
import { supabase } from '../supabaseClient'
import { setSession } from '../session'
import Icon from '../components/Icon'

export default function Login({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setLoading(true)
    setError('')
    const { data, error: err } = await supabase
      .from('users')
      .select('*')
      .eq('username', username.trim())
      .eq('password', password)
      .eq('status', 'Active')
      .maybeSingle()
    if (err) { setError(err.message); setLoading(false); return }
    if (!data) { setError('Invalid username or password.'); setLoading(false); return }
    setSession(data)
    onLogin(data)
    setLoading(false)
  }

  return (
    <div className="auth-wrap">
      <aside className="auth-side">
        <div className="auth-brand">
          <img src="/logo.png" alt="MediTrack" />
          <div>
            <div className="auth-brand-name">MediTrack</div>
            <div className="auth-brand-tag">Patient Monitoring</div>
          </div>
        </div>

        <div className="auth-hero">
          <h2>Integrated digital medical records, powered by RFID.</h2>
          <p>
            Scan an RFID wristband to instantly retrieve patient records,
            medications, and clinical notes — securely logged for every
            healthcare worker.
          </p>
          <div className="auth-points">
            <div className="auth-point"><span className="ico"><Icon name="shield" size={14} /></span> Role-based access for hospital staff</div>
            <div className="auth-point"><span className="ico"><Icon name="heart" size={14} /></span> Real-time medication monitoring</div>
            <div className="auth-point"><span className="ico"><Icon name="clipboard" size={14} /></span> Complete audit and scan history</div>
          </div>
        </div>

        <div className="auth-brand-tag" style={{ opacity: .7 }}>Raspberry Pi · RFID · Supabase</div>
      </aside>

      <main className="auth-main">
        <div className="auth-card">
          <h1>Welcome back</h1>
          <p className="sub">Sign in to your MediTrack account</p>

          <form onSubmit={submit} className="stack" style={{ gap: 15 }}>
            <div className="field">
              <label htmlFor="username">Username</label>
              <input
                id="username"
                name="username"
                className="input"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="Enter your username"
                autoComplete="username"
                required
                autoFocus
              />
            </div>
            <div className="field">
              <label htmlFor="password">Password</label>
              <div className="input-wrap">
                <input
                  id="password"
                  name="password"
                  className="input"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(v => !v)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  <Icon name={showPassword ? 'eyeOff' : 'eye'} size={16} />
                </button>
              </div>
            </div>
            {error && <div className="alert alert-error" style={{ marginTop: 0 }}>{error}</div>}
            <button className="btn btn-primary btn-block" disabled={loading} type="submit">
              {loading ? 'Signing in…' : 'Sign In'}
            </button>
          </form>

        </div>
      </main>
    </div>
  )
}
