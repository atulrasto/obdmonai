import { useEffect, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  getVehicle,
  getVehicleKpis,
  listTrips,
  getTripPoints,
  getDriverScore,
  getMaintenanceScore,
  getLatestTelemetry,
} from '../api/client'
import type {
  VehicleRead,
  VehicleKPIRead,
  DriverScoreResponse,
  MaintenanceResponse,
  TripPointRead,
  LatestTelemetryRead,
} from '../api/types'
import SpeedChart from '../components/SpeedChart'
import TrendPanel from '../components/TrendPanel'

const POLL_MS = 2000

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

function secsAgo(ts: string) {
  return Math.round((Date.now() - new Date(ts).getTime()) / 1000)
}

// ── Gauge bar ──────────────────────────────────────────────────────────────────
function Bar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  return (
    <div style={{ height: 6, background: '#e2e8f0', borderRadius: 3, overflow: 'hidden' }}>
      <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 3, transition: 'width 0.4s ease' }} />
    </div>
  )
}

// ── Single OBD gauge card ─────────────────────────────────────────────────────
function OBDCard({
  label, value, unit, max, color, pid, active, onClick,
}: {
  label: string; value: number | null; unit: string; max: number; color: string; pid?: string
  active?: boolean; onClick?: () => void
}) {
  const display = value != null ? `${value.toFixed(value < 10 ? 1 : 0)}` : '—'
  return (
    <div
      onClick={onClick}
      style={{
        background: active ? `${color}10` : '#fff',
        border: `1px solid ${active ? color : '#e2e8f0'}`,
        borderRadius: 8, padding: '0.85rem 1rem',
        display: 'flex', flexDirection: 'column', gap: 6,
        cursor: onClick ? 'pointer' : 'default',
        transition: 'border-color 0.15s, background 0.15s',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={{ fontSize: '0.72rem', color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</span>
        {pid && <span style={{ fontSize: '0.65rem', color: '#94a3b8', fontFamily: 'monospace' }}>{pid}</span>}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
        <span style={{ fontSize: '1.4rem', fontWeight: 700, color: value != null ? '#0f172a' : '#94a3b8', fontVariantNumeric: 'tabular-nums' }}>
          {display}
        </span>
        <span style={{ fontSize: '0.75rem', color: '#64748b' }}>{unit}</span>
      </div>
      {value != null && <Bar value={value} max={max} color={color} />}
      {onClick && (
        <div style={{ fontSize: '0.62rem', color: active ? color : '#94a3b8', marginTop: 2 }}>
          {active ? '▲ showing trend' : '▼ click for trend'}
        </div>
      )}
    </div>
  )
}

// ── GPS / IMU info row ────────────────────────────────────────────────────────
function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.3rem 0', borderBottom: '1px solid #f1f5f9', fontSize: '0.82rem' }}>
      <span style={{ color: '#64748b' }}>{label}</span>
      <span style={{ fontFamily: 'monospace', fontWeight: 500 }}>{value}</span>
    </div>
  )
}

export default function VehicleView() {
  const { id } = useParams<{ id: string }>()
  const [vehicle, setVehicle] = useState<VehicleRead | null>(null)
  const [kpi, setKpi] = useState<VehicleKPIRead | null>(null)
  const [driver, setDriver] = useState<DriverScoreResponse | null>(null)
  const [maint, setMaint] = useState<MaintenanceResponse | null>(null)
  const [points, setPoints] = useState<TripPointRead[]>([])
  const [live, setLive] = useState<LatestTelemetryRead | null>(null)
  const [liveAge, setLiveAge] = useState<number | null>(null)
  const [selectedParam, setSelectedParam] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // initial load
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

  // live telemetry polling every 2s
  useEffect(() => {
    if (!id) return

    async function fetchLive() {
      try {
        const data = await getLatestTelemetry(id!)
        setLive(data)
        setLiveAge(secsAgo(data.ts))
      } catch {
        // no data yet — stay null
      }
    }

    fetchLive()
    pollRef.current = setInterval(() => {
      fetchLive()
      setLiveAge((prev) => (prev != null ? prev + 2 : prev))
    }, POLL_MS)

    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [id])

  if (loading) return <div className="page">Loading…</div>
  if (!vehicle) return <div className="page">Vehicle not found.</div>

  const isRecent = liveAge != null && liveAge < 10

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

      {/* ── Live engine status bar ── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '0.75rem',
        marginBottom: '1.25rem', padding: '0.5rem 0.75rem',
        background: isRecent ? '#f0fdf4' : '#f8fafc',
        border: `1px solid ${isRecent ? '#bbf7d0' : '#e2e8f0'}`,
        borderRadius: 8, fontSize: '0.8rem',
      }}>
        <span style={{
          width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
          background: isRecent ? '#16a34a' : '#94a3b8',
          boxShadow: isRecent ? '0 0 0 3px #bbf7d0' : 'none',
          animation: isRecent ? 'pulse 1.4s ease-in-out infinite' : 'none',
        }} />
        {live ? (
          <>
            <span style={{ fontWeight: 600, color: isRecent ? '#15803d' : '#475569' }}>
              {isRecent ? 'LIVE' : 'LAST KNOWN'}
            </span>
            <span style={{ color: '#64748b' }}>
              {liveAge != null ? `${liveAge}s ago` : ''} ·
              IGN {live.ign ? <strong style={{ color: '#16a34a' }}>ON</strong> : <strong style={{ color: '#94a3b8' }}>OFF</strong>}
              {live.dtc.length > 0 && (
                <span style={{ marginLeft: '0.5rem', color: '#dc2626', fontWeight: 600 }}>
                  ⚠ DTC: {live.dtc.join(', ')}
                </span>
              )}
            </span>
          </>
        ) : (
          <span style={{ color: '#94a3b8' }}>No live data — start the simulator or connect a device</span>
        )}
      </div>

      {/* ── Live OBD gauges ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(155px, 1fr))', gap: '0.75rem', marginBottom: '1rem' }}>
        {([
          { key: 'obd_rpm',         label: 'Engine RPM',   pid: '0x0C', value: live?.obd_rpm ?? null,                                                         unit: 'rpm',  max: 6000, color: '#6366f1' },
          { key: 'obd_speed',       label: 'Speed',        pid: '0x0D', value: live?.obd_speed ?? null,                                                        unit: 'km/h', max: 120,  color: '#0ea5e9' },
          { key: 'obd_coolant',     label: 'Coolant Temp', pid: '0x05', value: live?.obd_coolant ?? null,                                                      unit: '°C',   max: 120,
            color: (live?.obd_coolant ?? 0) > 100 ? '#dc2626' : (live?.obd_coolant ?? 0) > 80 ? '#16a34a' : '#0ea5e9' },
          { key: 'obd_load',        label: 'Engine Load',  pid: '0x04', value: live?.obd_load ?? null,                                                         unit: '%',    max: 100,  color: '#f59e0b' },
          { key: 'obd_throttle',    label: 'Throttle',     pid: '0x11', value: live?.obd_throttle ?? null,                                                     unit: '%',    max: 100,  color: '#10b981' },
          { key: 'obd_intake_temp', label: 'Intake Temp',  pid: '0x0F', value: live?.obd_intake_temp ?? null,                                                  unit: '°C',   max: 80,   color: '#8b5cf6' },
          { key: 'obd_fuel_level',  label: 'Fuel Level',   pid: '0x2F', value: live?.obd_fuel_level ?? null,                                                   unit: '%',    max: 100,
            color: (live?.obd_fuel_level ?? 100) < 15 ? '#dc2626' : (live?.obd_fuel_level ?? 100) < 30 ? '#f59e0b' : '#16a34a' },
          { key: 'obd_run_time',    label: 'Run Time',     pid: '0x1F', value: live?.obd_run_time != null ? Math.round(live.obd_run_time / 60) : null,         unit: 'min',  max: 480,  color: '#64748b' },
        ] as const).map((card) => (
          <OBDCard
            key={card.key}
            label={card.label}
            pid={card.pid}
            value={card.value}
            unit={card.unit}
            max={card.max}
            color={card.color}
            active={selectedParam === card.key}
            onClick={() => setSelectedParam(selectedParam === card.key ? null : card.key)}
          />
        ))}
      </div>

      {/* ── Trend panel (opens below gauges when a card is selected) ── */}
      {selectedParam && id && (
        <TrendPanel
          vehicleId={id}
          param={selectedParam}
          onClose={() => setSelectedParam(null)}
        />
      )}

      {/* ── GPS + IMU info ── */}
      {live && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
          <div className="card" style={{ padding: '1rem' }}>
            <div style={{ fontWeight: 600, fontSize: '0.8rem', marginBottom: '0.5rem', color: '#475569' }}>GPS</div>
            <InfoRow label="Latitude"  value={live.gps_lat?.toFixed(6) ?? '—'} />
            <InfoRow label="Longitude" value={live.gps_lon?.toFixed(6) ?? '—'} />
            <InfoRow label="Altitude"  value={live.gps_alt != null ? `${live.gps_alt.toFixed(1)} m` : '—'} />
            <InfoRow label="Heading"   value={live.gps_hdg != null ? `${live.gps_hdg.toFixed(1)} °` : '—'} />
            <InfoRow label="GPS Speed" value={live.gps_spd != null ? `${(live.gps_spd * 3.6).toFixed(1)} km/h` : '—'} />
          </div>
          <div className="card" style={{ padding: '1rem' }}>
            <div style={{ fontWeight: 600, fontSize: '0.8rem', marginBottom: '0.5rem', color: '#475569' }}>IMU (m/s²)</div>
            <InfoRow label="Accel X (forward/braking)" value={live.imu_ax?.toFixed(3) ?? '—'} />
            <InfoRow label="Accel Y (lateral/cornering)" value={live.imu_ay?.toFixed(3) ?? '—'} />
            <InfoRow label="Accel Z (vertical/gravity)"  value={live.imu_az?.toFixed(3) ?? '—'} />
          </div>
        </div>
      )}

      {/* ── KPIs (24h aggregates) ── */}
      <div style={{ fontSize: '0.72rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '0.5rem' }}>
        24-hour aggregates
      </div>
      <div className="kpi-grid" aria-label="Vehicle KPIs" style={{ marginBottom: '1.5rem' }}>
        <div className="kpi-card">
          <div className="kpi-label">Distance</div>
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

      {/* ── ML scores ── */}
      <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        <div className="card" style={{ flex: 1, minWidth: 200 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div className={`score-ring ${scoreClass(driver?.score ?? null)}`}>
              {driver?.score != null ? Math.round(driver.score) : '?'}
            </div>
            <div>
              <div style={{ fontWeight: 600 }}>Driver Score</div>
              <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Last {driver?.window_hours ?? 24}h</div>
            </div>
          </div>
        </div>
        <div className="card" style={{ flex: 1, minWidth: 200 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div className={`score-ring ${maint?.is_anomaly ? 'score-poor' : 'score-good'}`}>
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

      {/* ── Speed chart ── */}
      {points.length > 0 ? (
        <SpeedChart points={points} title="Most recent trip — Speed & RPM" />
      ) : (
        <div className="card" style={{ color: '#94a3b8', textAlign: 'center', padding: '2rem' }}>
          No trip data in the last 24 hours
        </div>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
      `}</style>
    </div>
  )
}
