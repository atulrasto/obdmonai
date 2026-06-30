import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { listVehicles, createVehicle } from '../api/client'
import type { VehicleRead } from '../api/types'

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString([], { dateStyle: 'medium' })
}

export default function Vehicles() {
  const [vehicles, setVehicles] = useState<VehicleRead[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [vin, setVin] = useState('')
  const [make, setMake] = useState('')
  const [model, setModel] = useState('')
  const [year, setYear] = useState(String(new Date().getFullYear()))
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  async function reload() {
    const data = await listVehicles()
    setVehicles(data)
  }

  useEffect(() => {
    reload().finally(() => setLoading(false))
  }, [])

  async function handleAdd(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await createVehicle({ vin: vin.toUpperCase(), make, model_name: model, year: parseInt(year, 10) })
      setShowForm(false)
      setVin('')
      setMake('')
      setModel('')
      setYear(String(new Date().getFullYear()))
      await reload()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail ?? 'Failed to add vehicle — VIN must be unique (17 chars).')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Vehicles</h1>
        <button
          className="btn btn-primary"
          onClick={() => { setShowForm(!showForm); setError(null) }}
        >
          {showForm ? 'Cancel' : '+ Add vehicle'}
        </button>
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ fontSize: '0.9rem', marginBottom: '1rem' }}>Register new vehicle</h3>
          {error && <div className="error-msg">{error}</div>}
          <form onSubmit={handleAdd}>
            <div className="form-group">
              <label>VIN (17 characters)</label>
              <input
                value={vin}
                onChange={(e) => setVin(e.target.value.toUpperCase())}
                placeholder="1HGCM82633A004352"
                maxLength={17}
                minLength={17}
                style={{ fontFamily: 'monospace', letterSpacing: '0.05em' }}
                required
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 120px', gap: '1rem' }}>
              <div className="form-group">
                <label>Make</label>
                <input value={make} onChange={(e) => setMake(e.target.value)} placeholder="Volvo" required />
              </div>
              <div className="form-group">
                <label>Model</label>
                <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="FH16" required />
              </div>
              <div className="form-group">
                <label>Year</label>
                <input
                  type="number"
                  min="1990"
                  max="2100"
                  value={year}
                  onChange={(e) => setYear(e.target.value)}
                  required
                />
              </div>
            </div>
            <button className="btn btn-primary" type="submit" disabled={submitting}>
              {submitting ? 'Saving…' : 'Add vehicle'}
            </button>
          </form>
        </div>
      )}

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8' }}>Loading…</div>
        ) : vehicles.length === 0 ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8' }}>
            No vehicles yet — add your first vehicle above, then register an OBU on the Devices page.
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>VIN</th>
                <th>Make / Model</th>
                <th>Year</th>
                <th>Added</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {vehicles.map((v) => (
                <tr key={v.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/vehicles/${v.id}`)}>
                  <td style={{ fontFamily: 'monospace', fontSize: '0.85rem', letterSpacing: '0.03em' }}>{v.vin}</td>
                  <td style={{ fontWeight: 500 }}>{v.make} {v.model_name}</td>
                  <td>{v.year}</td>
                  <td style={{ fontSize: '0.8rem', color: '#64748b' }}>{fmtDate(v.created_at)}</td>
                  <td>
                    <button
                      className="btn btn-secondary"
                      style={{ padding: '0.25rem 0.75rem', fontSize: '0.75rem' }}
                      onClick={(e) => { e.stopPropagation(); navigate(`/vehicles/${v.id}`) }}
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {vehicles.length > 0 && (
        <div style={{ marginTop: '1rem', fontSize: '0.8rem', color: '#94a3b8' }}>
          Click any row to view live KPIs, trips, and ML scores for that vehicle.
          Go to <strong>Devices</strong> to attach an OBU to a vehicle.
        </div>
      )}
    </div>
  )
}
