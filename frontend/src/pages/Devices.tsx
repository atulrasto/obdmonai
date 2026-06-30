import { useEffect, useState, type FormEvent } from 'react'
import { listVehicles, listDevices, createDevice } from '../api/client'
import type { VehicleRead, DeviceRead } from '../api/types'

export default function Devices() {
  const [vehicles, setVehicles] = useState<VehicleRead[]>([])
  const [devices, setDevices] = useState<DeviceRead[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [vehicleId, setVehicleId] = useState('')
  const [serial, setSerial] = useState('')
  const [firmware, setFirmware] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function reload() {
    const [v, d] = await Promise.all([listVehicles(), listDevices()])
    setVehicles(v)
    setDevices(d)
  }

  useEffect(() => {
    reload().finally(() => setLoading(false))
  }, [])

  async function handleAdd(e: FormEvent) {
    e.preventDefault()
    if (!vehicleId || !serial) return
    setSubmitting(true)
    setError(null)
    try {
      await createDevice({ vehicle_id: vehicleId, serial, firmware_version: firmware || undefined })
      setShowForm(false)
      setSerial('')
      setFirmware('')
      await reload()
    } catch {
      setError('Failed to add device — check serial is unique.')
    } finally {
      setSubmitting(false)
    }
  }

  const vehicleMap = new Map(vehicles.map((v) => [v.id, v]))

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Devices</h1>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancel' : '+ Add device'}
        </button>
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ fontSize: '0.9rem', marginBottom: '1rem' }}>Register new OBU</h3>
          {error && <div className="error-msg">{error}</div>}
          <form onSubmit={handleAdd}>
            <div className="form-group">
              <label>Vehicle</label>
              <select value={vehicleId} onChange={(e) => setVehicleId(e.target.value)} required>
                <option value="">Select vehicle…</option>
                {vehicles.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.make} {v.model_name} — {v.vin}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label>Serial number</label>
              <input value={serial} onChange={(e) => setSerial(e.target.value)} placeholder="ESP32-XXXXXX" required />
            </div>
            <div className="form-group">
              <label>Firmware version (optional)</label>
              <input value={firmware} onChange={(e) => setFirmware(e.target.value)} placeholder="1.0.0" />
            </div>
            <button className="btn btn-primary" type="submit" disabled={submitting}>
              {submitting ? 'Registering…' : 'Register'}
            </button>
          </form>
        </div>
      )}

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8' }}>Loading…</div>
        ) : devices.length === 0 ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8' }}>No devices registered</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Serial</th>
                <th>Vehicle</th>
                <th>Firmware</th>
                <th>Provisioned</th>
              </tr>
            </thead>
            <tbody>
              {devices.map((d) => {
                const v = vehicleMap.get(d.vehicle_id)
                return (
                  <tr key={d.id}>
                    <td style={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>{d.serial}</td>
                    <td>{v ? `${v.make} ${v.model_name}` : d.vehicle_id.slice(0, 8) + '…'}</td>
                    <td>{d.firmware_version ?? '—'}</td>
                    <td style={{ fontSize: '0.8rem', color: '#64748b' }}>
                      {d.provisioned_at ? new Date(d.provisioned_at).toLocaleDateString() : '—'}
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
