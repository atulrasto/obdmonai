import { useEffect, useState, type FormEvent } from 'react'
import { listVehicles, listGeofences, createGeofence, deleteGeofence } from '../api/client'
import type { VehicleRead, GeofenceRead } from '../api/types'

export default function Geofences() {
  const [vehicles, setVehicles] = useState<VehicleRead[]>([])
  const [geofences, setGeofences] = useState<GeofenceRead[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [vehicleId, setVehicleId] = useState('')
  const [gfName, setGfName] = useState('')
  const [lat, setLat] = useState('')
  const [lon, setLon] = useState('')
  const [radius, setRadius] = useState('500')
  const [submitting, setSubmitting] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function reload() {
    const [v, g] = await Promise.all([listVehicles(), listGeofences()])
    setVehicles(v)
    setGeofences(g)
  }

  useEffect(() => {
    reload().finally(() => setLoading(false))
  }, [])

  async function handleAdd(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await createGeofence({
        name: gfName,
        center_lat: parseFloat(lat),
        center_lon: parseFloat(lon),
        radius_m: parseInt(radius, 10),
        vehicle_id: vehicleId || null,
      })
      setShowForm(false)
      setVehicleId('')
      setGfName('')
      setLat('')
      setLon('')
      setRadius('500')
      await reload()
    } catch {
      setError('Failed to create geofence.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDelete(id: string) {
    setDeleting(id)
    try {
      await deleteGeofence(id)
      await reload()
    } finally {
      setDeleting(null)
    }
  }

  const vehicleMap = new Map(vehicles.map((v) => [v.id, v]))

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Geofences</h1>
        <button className="btn btn-primary" onClick={() => { setShowForm(!showForm); setError(null) }}>
          {showForm ? 'Cancel' : '+ Add geofence'}
        </button>
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ fontSize: '0.9rem', marginBottom: '1rem' }}>New geofence</h3>
          {error && <div className="error-msg">{error}</div>}
          <form onSubmit={handleAdd}>
            <div className="form-group">
              <label>Vehicle <span style={{ color: '#94a3b8', fontWeight: 400 }}>(optional — leave blank for fleet-wide)</span></label>
              <select value={vehicleId} onChange={(e) => setVehicleId(e.target.value)}>
                <option value="">All vehicles (fleet-wide)</option>
                {vehicles.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.make} {v.model_name} — {v.vin}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label>Name</label>
              <input value={gfName} onChange={(e) => setGfName(e.target.value)} placeholder="Warehouse A" required />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div className="form-group">
                <label>Latitude</label>
                <input type="number" step="any" value={lat} onChange={(e) => setLat(e.target.value)} placeholder="18.5204" required />
              </div>
              <div className="form-group">
                <label>Longitude</label>
                <input type="number" step="any" value={lon} onChange={(e) => setLon(e.target.value)} placeholder="73.8567" required />
              </div>
            </div>
            <div className="form-group">
              <label>Radius (metres)</label>
              <input type="number" min="50" max="50000" value={radius} onChange={(e) => setRadius(e.target.value)} required />
            </div>
            <button className="btn btn-primary" type="submit" disabled={submitting}>
              {submitting ? 'Saving…' : 'Save geofence'}
            </button>
          </form>
        </div>
      )}

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8' }}>Loading…</div>
        ) : geofences.length === 0 ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8' }}>No geofences defined yet</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Vehicle</th>
                <th>Centre</th>
                <th>Radius</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {geofences.map((g) => {
                const v = g.vehicle_id ? vehicleMap.get(g.vehicle_id) : null
                return (
                  <tr key={g.id}>
                    <td style={{ fontWeight: 500 }}>{g.name}</td>
                    <td style={{ fontSize: '0.85rem', color: v ? '#0f172a' : '#94a3b8' }}>
                      {v ? `${v.make} ${v.model_name} (${v.vin})` : 'Fleet-wide'}
                    </td>
                    <td style={{ fontSize: '0.8rem', fontFamily: 'monospace', color: '#64748b' }}>
                      {g.center_lat.toFixed(5)}, {g.center_lon.toFixed(5)}
                    </td>
                    <td>{g.radius_m} m</td>
                    <td>
                      <span className={`badge ${g.is_active ? 'badge-cleared' : 'badge-warning'}`}>
                        {g.is_active ? 'active' : 'inactive'}
                      </span>
                    </td>
                    <td>
                      <button
                        className="btn btn-danger"
                        style={{ padding: '0.25rem 0.625rem', fontSize: '0.75rem' }}
                        disabled={deleting === g.id}
                        onClick={() => handleDelete(g.id)}
                      >
                        {deleting === g.id ? '…' : 'Delete'}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
