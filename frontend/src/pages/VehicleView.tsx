import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  getVehicle,
  getVehicleKpis,
  listTrips,
  getTripPoints,
  getDriverScore,
  getMaintenanceScore,
} from '../api/client'
import type {
  VehicleRead,
  VehicleKPIRead,
  DriverScoreResponse,
  MaintenanceResponse,
  TripPointRead,
} from '../api/types'
import SpeedChart from '../components/SpeedChart'

function fmtSec(sec: number): string {
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

function scoreClass(score: number | null) {
  if (score == null) return 'score-mid'
  if (score >= 70) return 'score-good'
  if (score >= 45) return 'score-mid'
  return 'score-poor'
}

export default function VehicleView() {
  const { id } = useParams<{ id: string }>()
  const [vehicle, setVehicle] = useState<VehicleRead | null>(null)
  const [kpi, setKpi] = useState<VehicleKPIRead | null>(null)
  const [driver, setDriver] = useState<DriverScoreResponse | null>(null)
  const [maint, setMaint] = useState<MaintenanceResponse | null>(null)
  const [points, setPoints] = useState<TripPointRead[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!id) return
    const now = new Date().toISOString()
    const from = new Date(Date.now() - 86_400_000).toISOString()

    async function load() {
      try {
        const [v, k, d, m, trips] = await Promise.all([
          getVehicle(id!),
          getVehicleKpis(id!, from, now),
          getDriverScore(id!),
          getMaintenanceScore(id!),
          listTrips(id!, from, now),
        ])
        setVehicle(v)
        setKpi(k)
        setDriver(d)
        setMaint(m)

        // Load the most recent trip's points for the chart
        if (trips.length > 0) {
          const latest = trips[trips.length - 1]
          const pts = await getTripPoints(latest.trip_id)
          setPoints(pts)
        }
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [id])

  if (loading) return <div className="page">Loading…</div>
  if (!vehicle) return <div className="page">Vehicle not found.</div>

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">{vehicle.make} {vehicle.model_name}</h1>
          <div style={{ fontSize: '0.8rem', color: '#64748b' }}>{vehicle.year} · {vehicle.vin}</div>
        </div>
        <Link to={`/vehicles/${id}/trips`} className="btn btn-secondary">
          View Trips Map
        </Link>
      </div>

      {/* KPIs */}
      <div className="kpi-grid" aria-label="Vehicle KPIs">
        <div className="kpi-card">
          <div className="kpi-label">Distance (24h)</div>
          <div className="kpi-value">{kpi ? `${kpi.distance_km.toFixed(1)} km` : '—'}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Drive time</div>
          <div className="kpi-value">{kpi ? fmtSec(kpi.drive_time_sec) : '—'}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Avg speed</div>
          <div className="kpi-value">{kpi?.avg_speed != null ? `${kpi.avg_speed.toFixed(0)} km/h` : '—'}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Max speed</div>
          <div className="kpi-value">{kpi?.max_speed != null ? `${kpi.max_speed.toFixed(0)} km/h` : '—'}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Harsh events</div>
          <div className="kpi-value">{kpi?.harsh_events ?? '—'}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Readings</div>
          <div className="kpi-value">{kpi?.reading_count ?? '—'}</div>
        </div>
      </div>

      {/* ML scores */}
      <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        <div className="card" style={{ flex: 1, minWidth: 200 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div className={`score-ring ${scoreClass(driver?.score ?? null)}`}>
              {driver?.score != null ? Math.round(driver.score) : '?'}
            </div>
            <div>
              <div style={{ fontWeight: 600 }}>Driver Score</div>
              <div style={{ fontSize: '0.75rem', color: '#64748b' }}>
                Last {driver?.window_hours ?? 24}h
              </div>
            </div>
          </div>
        </div>
        <div className="card" style={{ flex: 1, minWidth: 200 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div
              className={`score-ring ${maint?.is_anomaly ? 'score-poor' : 'score-good'}`}
            >
              {maint?.is_anomaly == null ? '?' : maint.is_anomaly ? '⚠' : '✓'}
            </div>
            <div>
              <div style={{ fontWeight: 600 }}>Maintenance</div>
              <div style={{ fontSize: '0.75rem', color: '#64748b' }}>
                {maint?.is_anomaly ? 'Anomaly detected' : 'No anomaly'}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Chart */}
      {points.length > 0 ? (
        <SpeedChart points={points} title="Most recent trip — Speed & RPM" />
      ) : (
        <div className="card" style={{ color: '#94a3b8', textAlign: 'center', padding: '2rem' }}>
          No trip data in the last 24 hours
        </div>
      )}
    </div>
  )
}
