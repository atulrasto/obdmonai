import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

const NAV_OWNER = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/vehicles', label: 'Vehicles', end: false },
  { to: '/devices', label: 'Devices', end: false },
  { to: '/geofences', label: 'Geofences', end: false },
  { to: '/alerts', label: 'Alerts', end: false },
  { to: '/reports', label: 'Reports', end: false },
  { to: '/fleetview', label: 'FleetView AI', end: false },
]

const NAV_SUPERADMIN = [
  { to: '/admin', label: 'Clients', end: true },
]

export default function Layout() {
  const { logout, role } = useAuth()
  const nav = role === 'superadmin' ? NAV_SUPERADMIN : NAV_OWNER

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-brand">⬡ obdmonai</div>
        {role === 'superadmin' && (
          <div style={{ padding: '0 1.25rem 0.75rem', fontSize: '0.7rem', fontWeight: 600, color: '#f59e0b', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Superadmin
          </div>
        )}
        <nav>
          {nav.map(({ to, label, end }) => (
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
        <div style={{ marginTop: 'auto', padding: '0 1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <NavLink
            to="/change-password"
            style={({ isActive }) => ({
              display: 'block', padding: '0.45rem 0.75rem', borderRadius: 6,
              fontSize: '0.85rem', textDecoration: 'none',
              color: isActive ? '#fff' : '#94a3b8',
              background: isActive ? '#334155' : 'transparent',
            })}
          >
            🔑 Change Password
          </NavLink>
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
