import { useState } from 'react'
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import Icon from './Icon'

const GROUPS = [
  {
    label: 'Clinical',
    items: [
      { to: '/', label: 'Dashboard', icon: 'dashboard', end: true },
      { to: '/patients', label: 'Patients', icon: 'users' },
      { to: '/rfid', label: 'RFID Tags', icon: 'rfid' },
    ],
  },
  {
    label: 'Activity',
    items: [
      { to: '/scans', label: 'Scan Logs', icon: 'clipboard' },
      { to: '/audit', label: 'Audit Logs', icon: 'shield' },
    ],
  },
]

function crumbFor(pathname) {
  if (pathname === '/') return 'Dashboard'
  if (pathname.startsWith('/patients/')) return 'Patient Record'
  if (pathname.startsWith('/patients')) return 'Patients'
  if (pathname.startsWith('/rfid')) return 'RFID Tags'
  if (pathname.startsWith('/scans')) return 'Scan Logs'
  if (pathname.startsWith('/audit')) return 'Audit Logs'
  if (pathname.startsWith('/users')) return 'User Management'
  return 'Dashboard'
}

export default function Layout({ user, onLogout }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [open, setOpen] = useState(false)

  function logout() { onLogout(); navigate('/login') }
  const close = () => setOpen(false)
  const initials = user?.name?.split(' ').map(w => w[0]).slice(0, 2).join('') || 'U'
  const linkClass = ({ isActive }) => 'side-link' + (isActive ? ' active' : '')
  const today = new Date().toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })

  return (
    <div className="app-shell">
      <aside className={'sidebar' + (open ? ' open' : '')}>
        <NavLink to="/" className="sidebar-brand" onClick={close}>
          <img src="/logo.png" alt="MediTrack logo" />
          <div>
            <div className="sidebar-brand-name">MediTrack</div>
            <div className="sidebar-brand-tag">Patient Monitoring</div>
          </div>
        </NavLink>

        {GROUPS.map(group => (
          <div key={group.label}>
            <div className="sidebar-label">{group.label}</div>
            <nav className="sidebar-nav" style={{ marginBottom: 10 }}>
              {group.items.map(item => (
                <NavLink key={item.to} to={item.to} end={item.end} className={linkClass} onClick={close}>
                  <Icon name={item.icon} size={18} />
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
        ))}

        {user?.role === 'Administrator' && (
          <div>
            <div className="sidebar-label">Administration</div>
            <nav className="sidebar-nav">
              <NavLink to="/users" className={linkClass} onClick={close}>
                <Icon name="settings" size={18} />
                User Management
              </NavLink>
            </nav>
          </div>
        )}

        <div className="sidebar-spacer" />

        <div className="sidebar-footer">
          <div className="side-user">
            <div className="avatar">{initials}</div>
            <div style={{ minWidth: 0 }}>
              <div className="side-user-name">{user?.name}</div>
              <div className="side-user-role">{user?.role}</div>
            </div>
          </div>
          <button className="side-logout" onClick={logout}>
            <Icon name="logout" size={15} />
            Sign out
          </button>
        </div>
      </aside>

      <div className={'overlay' + (open ? ' show' : '')} onClick={close} />

      <div className="app-main">
        <header className="topbar">
          <div className="topbar-left">
            <button className="icon-btn mobile-menu" onClick={() => setOpen(o => !o)} aria-label="Open menu">
              <Icon name="menu" size={18} />
            </button>
            <div className="breadcrumb">
              <span className="crumb-home">MediTrack</span>
              <Icon name="chevronRight" size={13} />
              <span className="crumb-current">{crumbFor(location.pathname)}</span>
            </div>
          </div>

          <div className="topbar-right">
            <div className="topbar-date">
              <Icon name="calendar" size={14} />
              {today}
            </div>
            <div className="topbar-user">
              <div className="avatar">{initials}</div>
              <div>
                <div className="topbar-user-name">{user?.name}</div>
                <div className="topbar-user-role">{user?.role}</div>
              </div>
            </div>
          </div>
        </header>

        <main className="page">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
