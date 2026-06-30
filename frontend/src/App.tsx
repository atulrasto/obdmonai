import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import Layout from './components/Layout'
import Login from './pages/Login'
import ChangePassword from './pages/ChangePassword'
import Dashboard from './pages/Dashboard'
import SuperAdmin from './pages/SuperAdmin'
import VehicleView from './pages/VehicleView'
import Trips from './pages/Trips'
import Alerts from './pages/Alerts'
import Devices from './pages/Devices'
import Vehicles from './pages/Vehicles'
import Geofences from './pages/Geofences'
import Reports from './pages/Reports'
import FleetView from './pages/FleetView'

/** Redirect to /login if not authenticated. */
function RequireAuth() {
  const { token } = useAuth()
  return token ? <Outlet /> : <Navigate to="/login" replace />
}

/** Redirect to /change-password if must_change_password flag is set. */
function RequirePasswordOk() {
  const { mustChangePassword } = useAuth()
  return mustChangePassword ? <Navigate to="/change-password" replace /> : <Outlet />
}

/** Redirect non-superadmin to dashboard. */
function RequireSuperAdmin({ children }: { children: React.ReactNode }) {
  const { role } = useAuth()
  return role === 'superadmin' ? <>{children}</> : <Navigate to="/" replace />
}

/** Home route: superadmin → /admin, others → Dashboard. */
function HomeRoute() {
  const { role } = useAuth()
  return role === 'superadmin' ? <Navigate to="/admin" replace /> : <Dashboard />
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Public */}
          <Route path="/login" element={<Login />} />

          {/* Authenticated but password change may be pending */}
          <Route element={<RequireAuth />}>
            <Route path="/change-password" element={<ChangePassword />} />

            {/* Authenticated + password ok */}
            <Route element={<RequirePasswordOk />}>
              <Route element={<Layout />}>
                <Route index element={<HomeRoute />} />
                <Route
                  path="/admin"
                  element={
                    <RequireSuperAdmin>
                      <SuperAdmin />
                    </RequireSuperAdmin>
                  }
                />
                <Route path="/vehicles" element={<Vehicles />} />
                <Route path="/vehicles/:id" element={<VehicleView />} />
                <Route path="/vehicles/:id/trips" element={<Trips />} />
                <Route path="/alerts" element={<Alerts />} />
                <Route path="/devices" element={<Devices />} />
                <Route path="/geofences" element={<Geofences />} />
                <Route path="/reports" element={<Reports />} />
                <Route path="/fleetview" element={<FleetView />} />
              </Route>
            </Route>
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
