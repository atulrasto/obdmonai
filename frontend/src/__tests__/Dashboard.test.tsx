/// <reference types="vitest/globals" />
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import * as client from '../api/client'
import { AuthProvider } from '../contexts/AuthContext'
import Dashboard from '../pages/Dashboard'

// Mock the entire API client
vi.mock('../api/client')

// A valid-ish base64url JWT payload so AuthProvider can parse client_id
const MOCK_TOKEN =
  'h.eyJzdWIiOiJ1MSIsImNsaWVudF9pZCI6ImMxIiwicm9sZSI6Im93bmVyIiwiZXhwIjo5OTk5OTk5OTk5fQ.sig'

function renderWithProviders(ui: React.ReactElement) {
  localStorage.setItem('token', MOCK_TOKEN)
  return render(
    <MemoryRouter>
      <AuthProvider>{ui}</AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
})

test('renders Fleet Dashboard heading', async () => {
  vi.mocked(client.listVehicles).mockResolvedValue([])
  vi.mocked(client.listFleet).mockResolvedValue([])

  renderWithProviders(<Dashboard />)

  await waitFor(() => expect(screen.getByText('Fleet Dashboard')).toBeInTheDocument())
})

test('renders vehicle cards from API', async () => {
  vi.mocked(client.listVehicles).mockResolvedValue([
    {
      id: 'v1',
      client_id: 'c1',
      vin: 'WVWZZZ3BZ3E000001',
      make: 'Volvo',
      model_name: 'FH16',
      year: 2023,
      created_at: '2024-01-01T00:00:00Z',
    },
    {
      id: 'v2',
      client_id: 'c1',
      vin: 'WVWZZZ3BZ3E000002',
      make: 'Scania',
      model_name: 'R450',
      year: 2022,
      created_at: '2024-01-01T00:00:00Z',
    },
  ])
  vi.mocked(client.listFleet).mockResolvedValue([
    { vehicle_id: 'v1', reading_count: 200, distance_km: 120.5, last_seen: '2024-06-01T10:00:00Z', avg_speed: 75.0 },
    { vehicle_id: 'v2', reading_count: 150, distance_km: 88.3, last_seen: '2024-06-01T09:00:00Z', avg_speed: 62.1 },
  ])

  renderWithProviders(<Dashboard />)

  await waitFor(() => expect(screen.getByText(/Volvo/)).toBeInTheDocument())
  expect(screen.getByText(/Scania/)).toBeInTheDocument()
  expect(screen.getByText(/FH16/)).toBeInTheDocument()
  expect(screen.getByText(/R450/)).toBeInTheDocument()
})

test('shows empty state when no vehicles', async () => {
  vi.mocked(client.listVehicles).mockResolvedValue([])
  vi.mocked(client.listFleet).mockResolvedValue([])

  renderWithProviders(<Dashboard />)

  await waitFor(() =>
    expect(screen.getByText(/No vehicles registered yet/i)).toBeInTheDocument(),
  )
})
