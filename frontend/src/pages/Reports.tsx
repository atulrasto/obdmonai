import { useEffect, useState, type FormEvent } from 'react'
import { listVehicles, downloadVehicleReport } from '../api/client'
import type { VehicleRead } from '../api/types'

function toLocalDatetimeValue(date: Date): string {
  // Returns yyyy-MM-ddTHH:mm for <input type="datetime-local">
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export default function Reports() {
  const [vehicles, setVehicles] = useState<VehicleRead[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [fromVal, setFromVal] = useState(() => toLocalDatetimeValue(new Date(Date.now() - 7 * 86_400_000)))
  const [toVal, setToVal] = useState(() => toLocalDatetimeValue(new Date()))
  const [loading, setLoading] = useState(false)
  const [loadingVehicles, setLoadingVehicles] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    listVehicles()
      .then((v) => {
        setVehicles(v)
        if (v.length > 0) setSelectedId(v[0].id)
      })
      .finally(() => setLoadingVehicles(false))
  }, [])

  async function handleDownload(e: FormEvent) {
    e.preventDefault()
    if (!selectedId) return
    setError(null)
    setSuccess(false)
    setLoading(true)
    try {
      const fromIso = new Date(fromVal).toISOString()
      const toIso = new Date(toVal).toISOString()
      await downloadVehicleReport(selectedId, fromIso, toIso)
      setSuccess(true)
    } catch {
      setError('Failed to generate report. The vehicle may have no data in this period.')
    } finally {
      setLoading(false)
    }
  }

  const selectedVehicle = vehicles.find((v) => v.id === selectedId)

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Reports</h1>
      </div>

      <div className="card" style={{ maxWidth: 560 }}>
        <h3 style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: '1rem', color: '#475569' }}>
          Vehicle Performance PDF
        </h3>
        <form onSubmit={handleDownload}>
          <div className="form-group">
            <label>Vehicle</label>
            <select
              value={selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
              disabled={loadingVehicles}
              required
            >
              {loadingVehicles ? (
                <option>Loading…</option>
              ) : (
                vehicles.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.make} {v.model_name} — {v.vin}
                  </option>
                ))
              )}
            </select>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div className="form-group">
              <label>From</label>
              <input
                type="datetime-local"
                value={fromVal}
                onChange={(e) => setFromVal(e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label>To</label>
              <input
                type="datetime-local"
                value={toVal}
                onChange={(e) => setToVal(e.target.value)}
                required
              />
            </div>
          </div>
          {error && <div className="error-msg">{error}</div>}
          {success && (
            <div style={{ background: '#dcfce7', color: '#166534', padding: '0.625rem 0.875rem', borderRadius: '0.375rem', fontSize: '0.8rem', marginBottom: '1rem' }}>
              PDF downloaded for {selectedVehicle?.make} {selectedVehicle?.model_name}.
            </div>
          )}
          <button className="btn btn-primary" type="submit" disabled={loading || !selectedId}>
            {loading ? 'Generating…' : 'Download PDF'}
          </button>
        </form>
      </div>

      <div className="card" style={{ maxWidth: 560, marginTop: '1.5rem', background: '#f8fafc' }}>
        <div style={{ fontSize: '0.8rem', color: '#64748b', lineHeight: 1.7 }}>
          <strong>What's included:</strong>
          <ul style={{ marginTop: '0.5rem', paddingLeft: '1.25rem' }}>
            <li>Driving KPIs — distance, drive time, idle time, harsh events</li>
            <li>Average and maximum speed</li>
            <li>Up to 10 most recent trips with per-trip stats</li>
          </ul>
        </div>
      </div>
    </div>
  )
}
