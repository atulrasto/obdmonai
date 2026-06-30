import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listVehicles, listFleet } from '../api/client'
import type { VehicleRead, FleetVehicleRead } from '../api/types'

function isoNow() {
  return new Date().toISOString()
}
function iso24hAgo() {
  return new Date(Date.now() - 86_400_000).toISOString()
}

interface VehicleRow {
  vehicle: VehicleRead
  fleet: FleetVehicleRead | undefined
}

export default function Dashboard() {
  const [rows, setRows] = useState<VehicleRow[]>([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    async function load() {
      try {
        const [vehicles, fleet] = await Promise.all([
          listVehicles(),
          listFleet(iso24hAgo(), isoNow()),
        ])
        const fleetMap = new Map(fleet.map((f) => [f.vehicle_id, f]))
        setRows(vehicles.map((v) => ({ vehicle: v, fleet: fleetMap.get(v.id) })))
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  if (loading) return <div className="page">Loading…</div>

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Fleet Dashboard</h1>
        <span style={{ fontSize: '0.8rem', color: '#64748b' }}>{rows.length} vehicle{rows.length !== 1 ? 's' : ''}</span>
      </div>

      {rows.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', color: '#94a3b8', padding: '3rem' }}>
          No vehicles registered yet.
        </div>
      ) : (
        <div className="card-grid">
          {rows.map(({ vehicle, fleet }) => (
            <div
              key={vehicle.id}
              className="vehicle-card"
              role="button"
              tabIndex={0}
              onClick={() => navigate(`/vehicles/${vehicle.id}`)}
              onKeyDown={(e) => e.key === 'Enter' && navigate(`/vehicles/${vehicle.id}`)}
            >
              <div className="vehicle-make">{vehicle.make} {vehicle.model_name}</div>
              <div className="vehicle-sub">{vehicle.year} · {vehicle.vin}</div>
              <div className="vehicle-stats">
                <span>{fleet ? `${fleet.distance_km.toFixed(1)} km` : '—'}</span>
                <span>{fleet?.avg_speed != null ? `${fleet.avg_speed.toFixed(0)} km/h avg` : '—'}</span>
                {fleet?.last_seen && (
                  <span>Last: {new Date(fleet.last_seen).toLocaleDateString()}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
