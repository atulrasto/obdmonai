import axios from 'axios'
import type {
  TokenResponse,
  VehicleRead,
  VehicleCreateRequest,
  DeviceRead,
  DeviceCreateRequest,
  AlertRead,
  GeofenceRead,
  GeofenceCreateRequest,
  VehicleKPIRead,
  TripRead,
  TripPointRead,
  FleetVehicleRead,
  DriverScoreResponse,
  MaintenanceResponse,
  SummaryResponse,
  ClientRead,
  ClientCreateRequest,
  ClientCreateResponse,
} from './types'

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? '/api'

const ax = axios.create({ baseURL: BASE })

ax.interceptors.request.use((cfg) => {
  const token = localStorage.getItem('token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

ax.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  },
)

// ── Auth ──────────────────────────────────────────────────────────────────────

export const login = (email: string, password: string) =>
  ax.post<TokenResponse>('/auth/login', { email, password }).then((r) => r.data)

export const changePassword = (currentPassword: string, newPassword: string) =>
  ax
    .post<TokenResponse>('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    })
    .then((r) => r.data)

// ── Superadmin ────────────────────────────────────────────────────────────────

export const listAllClients = () =>
  ax.get<ClientRead[]>('/clients').then((r) => r.data)

export const adminCreateClient = (data: ClientCreateRequest) =>
  ax.post<ClientCreateResponse>('/clients', data).then((r) => r.data)

// ── Vehicles ──────────────────────────────────────────────────────────────────

export const listVehicles = () =>
  ax.get<VehicleRead[]>('/vehicles').then((r) => r.data)

export const getVehicle = (id: string) =>
  ax.get<VehicleRead>(`/vehicles/${id}`).then((r) => r.data)

export const createVehicle = (data: VehicleCreateRequest) =>
  ax.post<VehicleRead>('/vehicles', data).then((r) => r.data)

// ── Devices ───────────────────────────────────────────────────────────────────

export const listDevices = () =>
  ax.get<DeviceRead[]>('/devices').then((r) => r.data)

export const createDevice = (data: DeviceCreateRequest) =>
  ax.post<DeviceRead>('/devices', data).then((r) => r.data)

// ── Alerts ────────────────────────────────────────────────────────────────────

export const listAlerts = (params?: { state?: string; vehicle_id?: string }) =>
  ax.get<AlertRead[]>('/alerts', { params }).then((r) => r.data)

// ── Geofences ─────────────────────────────────────────────────────────────────

export const listGeofences = () =>
  ax.get<GeofenceRead[]>('/geofences').then((r) => r.data)

export const createGeofence = (data: GeofenceCreateRequest) =>
  ax.post<GeofenceRead>('/geofences', data).then((r) => r.data)

export const deleteGeofence = (id: string) =>
  ax.delete(`/geofences/${id}`)

// ── Analytics ─────────────────────────────────────────────────────────────────
// Backend uses alias="from" and alias="to" — NOT from_ts/to_ts

export const getVehicleKpis = (id: string, fromTs: string, toTs: string) =>
  ax
    .get<VehicleKPIRead>(`/analytics/vehicles/${id}/kpis`, {
      params: { from: fromTs, to: toTs },
    })
    .then((r) => r.data)

export const listTrips = (id: string, fromTs: string, toTs: string) =>
  ax
    .get<TripRead[]>(`/analytics/vehicles/${id}/trips`, {
      params: { from: fromTs, to: toTs },
    })
    .then((r) => r.data)

export const getTripPoints = (tripId: number) =>
  ax.get<TripPointRead[]>(`/analytics/trips/${tripId}/points`).then((r) => r.data)

export const listFleet = (fromTs: string, toTs: string) =>
  ax
    .get<FleetVehicleRead[]>('/analytics/fleet', {
      params: { from: fromTs, to: toTs },
    })
    .then((r) => r.data)

// ── ML Scores ─────────────────────────────────────────────────────────────────

export const getDriverScore = (id: string, hours = 24) =>
  ax
    .get<DriverScoreResponse>(`/scores/vehicles/${id}/driver`, { params: { hours } })
    .then((r) => r.data)

export const getMaintenanceScore = (id: string) =>
  ax.get<MaintenanceResponse>(`/scores/vehicles/${id}/maintenance`).then((r) => r.data)

// ── FleetView ─────────────────────────────────────────────────────────────────

export const getFleetViewSummary = (id: string, hours = 24) =>
  ax
    .get<SummaryResponse>(`/fleetview/vehicles/${id}/summary`, { params: { hours } })
    .then((r) => r.data)

// ── Reports (PDF) ─────────────────────────────────────────────────────────────

export const downloadVehicleReport = async (
  id: string,
  fromTs: string,
  toTs: string,
): Promise<void> => {
  const response = await ax.get(`/reports/vehicles/${id}/pdf`, {
    params: { from_ts: fromTs, to_ts: toTs },
    responseType: 'blob',
  })
  const url = window.URL.createObjectURL(new Blob([response.data as BlobPart], { type: 'application/pdf' }))
  const a = document.createElement('a')
  a.href = url
  a.download = `vehicle_report_${id.slice(0, 8)}.pdf`
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}
