import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import VehicleView from './pages/VehicleView'
import Trips from './pages/Trips'
import Alerts from './pages/Alerts'
import Devices from './pages/Devices'
import FleetView from './pages/FleetView'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { token } = useAuth()
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            element={
              <RequireAuth>
                <Layout />
              </RequireAuth>
            }
          >
            <Route index element={<Dashboard />} />
            <Route path="vehicles/:id" element={<VehicleView />} />
            <Route path="vehicles/:id/trips" element={<Trips />} />
            <Route path="alerts" element={<Alerts />} />
            <Route path="devices" element={<Devices />} />
            <Route path="fleetview" element={<FleetView />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
