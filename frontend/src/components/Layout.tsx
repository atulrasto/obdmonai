import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

const NAV = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/alerts', label: 'Alerts', end: false },
  { to: '/devices', label: 'Devices', end: false },
  { to: '/fleetview', label: 'FleetView AI', end: false },
]

export default function Layout() {
  const { logout } = useAuth()

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-brand">⬡ obdmonai</div>
        <nav>
          {NAV.map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => (isActive ? 'active' : '')}
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <div style={{ marginTop: 'auto', padding: '0 1rem' }}>
          <button className="btn btn-secondary" style={{ width: '100%' }} onClick={logout}>
            Sign out
          </button>
        </div>
      </aside>
      <div className="main-content">
        <Outlet />
      </div>
    </div>
  )
}
