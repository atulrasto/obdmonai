import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getVehicle, listTrips, getTripPoints } from '../api/client'
import type { TripRead, TripPointRead, VehicleRead } from '../api/types'
import TripMap from '../components/TripMap'

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })
}

export default function Trips() {
  const { id } = useParams<{ id: string }>()
  const [vehicle, setVehicle] = useState<VehicleRead | null>(null)
  const [trips, setTrips] = useState<TripRead[]>([])
  const [selected, setSelected] = useState<TripRead | null>(null)
  const [points, setPoints] = useState<TripPointRead[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingPoints, setLoadingPoints] = useState(false)

  useEffect(() => {
    if (!id) return
    const now = new Date().toISOString()
    const from = new Date(Date.now() - 7 * 86_400_000).toISOString()
    async function load() {
      try {
        const [v, t] = await Promise.all([getVehicle(id!), listTrips(id!, from, now)])
        setVehicle(v)
        setTrips(t)
        if (t.length > 0) setSelected(t[t.length - 1])
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [id])

  useEffect(() => {
    if (!selected) return
    setLoadingPoints(true)
    getTripPoints(selected.trip_id)
      .then(setPoints)
      .finally(() => setLoadingPoints(false))
  }, [selected?.trip_id])

  if (loading) return <div className="page">Loading…</div>

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">
          Trips — {vehicle ? `${vehicle.make} ${vehicle.model_name}` : '…'}
        </h1>
      </div>

      <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'flex-start' }}>
        {/* Trip list */}
        <div className="card" style={{ width: 260, flexShrink: 0 }}>
          <h3 style={{ fontSize: '0.8rem', color: '#64748b', marginBottom: '0.75rem' }}>
            RECENT TRIPS ({trips.length})
          </h3>
          {trips.length === 0 ? (
            <div style={{ color: '#94a3b8', fontSize: '0.875rem' }}>No trips found</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {[...trips].reverse().map((t) => (
                <button
                  key={t.trip_id}
                  onClick={() => setSelected(t)}
                  style={{
                    textAlign: 'left', background: selected?.trip_id === t.trip_id ? '#eff6ff' : 'transparent',
                    border: selected?.trip_id === t.trip_id ? '1px solid #bfdbfe' : '1px solid #e2e8f0',
                    borderRadius: 6, padding: '0.625rem', cursor: 'pointer',
                  }}
                >
                  <div style={{ fontSize: '0.8rem', fontWeight: 600 }}>{fmtDate(t.started_at)}</div>
                  <div style={{ fontSize: '0.75rem', color: '#64748b' }}>
                    {t.distance_km.toFixed(1)} km · {t.point_count} pts
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Map */}
        <div style={{ flex: 1 }}>
          {loadingPoints ? (
            <div style={{ height: 400, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f8fafc', borderRadius: 8 }}>
              Loading GPS points…
            </div>
          ) : (
            <TripMap points={points} height={480} />
          )}
        </div>
      </div>
    </div>
  )
}
