/// <reference types="vitest/globals" />
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { vi } from 'vitest'
import * as client from '../api/client'
import { AuthProvider } from '../contexts/AuthContext'
import VehicleView from '../pages/VehicleView'

vi.mock('../api/client')

const MOCK_TOKEN =
  'h.eyJzdWIiOiJ1MSIsImNsaWVudF9pZCI6ImMxIiwicm9sZSI6Im93bmVyIiwiZXhwIjo5OTk5OTk5OTk5fQ.sig'

const VEHICLE_ID = 'aaaaaaaa-0000-0000-0000-000000000001'

function renderVehicleView() {
  localStorage.setItem('token', MOCK_TOKEN)
  return render(
    <MemoryRouter initialEntries={[`/vehicles/${VEHICLE_ID}`]}>
      <AuthProvider>
        <Routes>
          <Route path="/vehicles/:id" element={<VehicleView />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
})

test('renders vehicle make and model', async () => {
  vi.mocked(client.getVehicle).mockResolvedValue({
    id: VEHICLE_ID,
    client_id: 'c1',
    vin: 'WVWZZZ3BZ3E100001',
    make: 'Mercedes',
    model_name: 'Actros',
    year: 2024,
    created_at: '2024-01-01T00:00:00Z',
  })
  vi.mocked(client.getVehicleKpis).mockResolvedValue({
    vehicle_id: VEHICLE_ID,
    from_ts: '2024-06-01T00:00:00Z',
    to_ts: '2024-06-02T00:00:00Z',
    reading_count: 500,
    distance_km: 250.4,
    drive_time_sec: 14400,
    idle_time_sec: 1800,
    harsh_events: 2,
    avg_speed: 82.1,
    max_speed: 110.0,
  })
  vi.mocked(client.getDriverScore).mockResolvedValue({
    vehicle_id: VEHICLE_ID,
    score: 78.5,
    window_hours: 24,
    computed_at: '2024-06-02T00:00:00Z',
  })
  vi.mocked(client.getMaintenanceScore).mockResolvedValue({
    vehicle_id: VEHICLE_ID,
    is_anomaly: false,
    anomaly_score: -0.12,
    window_hours: 168,
    computed_at: '2024-06-02T00:00:00Z',
  })
  vi.mocked(client.listTrips).mockResolvedValue([])

  renderVehicleView()

  await waitFor(() => expect(screen.getByText(/Mercedes/)).toBeInTheDocument())
  expect(screen.getByText(/Actros/)).toBeInTheDocument()
})

test('renders KPI cards with distance', async () => {
  vi.mocked(client.getVehicle).mockResolvedValue({
    id: VEHICLE_ID, client_id: 'c1', vin: 'AAAAA1', make: 'Volvo', model_name: 'FH',
    year: 2023, created_at: '2024-01-01T00:00:00Z',
  })
  vi.mocked(client.getVehicleKpis).mockResolvedValue({
    vehicle_id: VEHICLE_ID, from_ts: '', to_ts: '',
    reading_count: 100, distance_km: 95.0,
    drive_time_sec: 3600, idle_time_sec: 600, harsh_events: 1,
    avg_speed: 60.0, max_speed: 90.0,
  })
  vi.mocked(client.getDriverScore).mockResolvedValue({
    vehicle_id: VEHICLE_ID, score: 65.0, window_hours: 24, computed_at: '',
  })
  vi.mocked(client.getMaintenanceScore).mockResolvedValue({
    vehicle_id: VEHICLE_ID, is_anomaly: false, anomaly_score: -0.1, window_hours: 168, computed_at: '',
  })
  vi.mocked(client.listTrips).mockResolvedValue([])

  renderVehicleView()

  await waitFor(() => expect(screen.getByText(/95.0 km/)).toBeInTheDocument())
  expect(screen.getByLabelText('Vehicle KPIs')).toBeInTheDocument()
})

test('renders SpeedChart when trip points exist', async () => {
  vi.mocked(client.getVehicle).mockResolvedValue({
    id: VEHICLE_ID, client_id: 'c1', vin: 'B2', make: 'DAF', model_name: 'XG',
    year: 2024, created_at: '',
  })
  vi.mocked(client.getVehicleKpis).mockResolvedValue({
    vehicle_id: VEHICLE_ID, from_ts: '', to_ts: '',
    reading_count: 50, distance_km: 30.0, drive_time_sec: 1800,
    idle_time_sec: 0, harsh_events: 0, avg_speed: 60.0, max_speed: 80.0,
  })
  vi.mocked(client.getDriverScore).mockResolvedValue({
    vehicle_id: VEHICLE_ID, score: 80.0, window_hours: 24, computed_at: '',
  })
  vi.mocked(client.getMaintenanceScore).mockResolvedValue({
    vehicle_id: VEHICLE_ID, is_anomaly: false, anomaly_score: -0.05, window_hours: 168, computed_at: '',
  })
  vi.mocked(client.listTrips).mockResolvedValue([{
    trip_id: 1, vehicle_id: VEHICLE_ID, started_at: '2024-06-01T08:00:00Z',
    ended_at: '2024-06-01T08:30:00Z', point_count: 3,
    distance_km: 30.0, drive_time_sec: 1800, avg_speed: 60.0, max_speed: 80.0,
  }])
  vi.mocked(client.getTripPoints).mockResolvedValue([
    { ts: '2024-06-01T08:00:00Z', lat: 18.5, lon: 73.9, obd_speed: 60.0, obd_rpm: 1500.0, obd_coolant: 85.0, ign: true },
    { ts: '2024-06-01T08:15:00Z', lat: 18.51, lon: 73.91, obd_speed: 70.0, obd_rpm: 1800.0, obd_coolant: 87.0, ign: true },
    { ts: '2024-06-01T08:30:00Z', lat: 18.52, lon: 73.92, obd_speed: 55.0, obd_rpm: 1400.0, obd_coolant: 86.0, ign: true },
  ])

  renderVehicleView()

  // Chart title should appear once points are loaded
  await waitFor(() =>
    expect(screen.getByText(/Most recent trip/)).toBeInTheDocument(),
  )
})
