import { useEffect, useState } from 'react'
import { listVehicles, getFleetViewSummary } from '../api/client'
import type { VehicleRead, SummaryResponse } from '../api/types'

export default function FleetView() {
  const [vehicles, setVehicles] = useState<VehicleRead[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [hours, setHours] = useState(24)
  const [summary, setSummary] = useState<SummaryResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadingVehicles, setLoadingVehicles] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listVehicles()
      .then((v) => {
        setVehicles(v)
        if (v.length > 0) setSelectedId(v[0].id)
      })
      .finally(() => setLoadingVehicles(false))
  }, [])

  async function fetchSummary() {
    if (!selectedId) return
    setLoading(true)
    setError(null)
    try {
      const s = await getFleetViewSummary(selectedId, hours)
      setSummary(s)
    } catch {
      setError('Could not retrieve summary — vehicle may have no telemetry in this window.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">FleetView AI</h1>
      </div>

      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div className="form-group" style={{ marginBottom: 0, flex: 1, minWidth: 200 }}>
            <label>Vehicle</label>
            <select value={selectedId} onChange={(e) => setSelectedId(e.target.value)} disabled={loadingVehicles}>
              {vehicles.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.make} {v.model_name} — {v.vin}
                </option>
              ))}
            </select>
          </div>
          <div className="form-group" style={{ marginBottom: 0, width: 120 }}>
            <label>Window</label>
            <select value={hours} onChange={(e) => setHours(Number(e.target.value))}>
              <option value={6}>6 hours</option>
              <option value={24}>24 hours</option>
              <option value={48}>48 hours</option>
              <option value={168}>7 days</option>
            </select>
          </div>
          <button className="btn btn-primary" onClick={fetchSummary} disabled={loading || !selectedId}>
            {loading ? 'Generating…' : 'Generate summary'}
          </button>
        </div>
      </div>

      {error && <div className="error-msg">{error}</div>}

      {summary && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
            <h3 style={{ fontSize: '0.875rem', fontWeight: 600, color: '#475569' }}>
              AI Fleet Summary
            </h3>
            <span style={{ fontSize: '0.7rem', color: '#94a3b8' }}>
              {new Date(summary.computed_at).toLocaleString()}
            </span>
          </div>
          <div className="summary-box">{summary.summary}</div>
        </div>
      )}

      {!summary && !loading && !error && (
        <div className="card" style={{ textAlign: 'center', color: '#94a3b8', padding: '3rem' }}>
          Select a vehicle and click "Generate summary" to get an AI-powered fleet health briefing.
        </div>
      )}
    </div>
  )
}
