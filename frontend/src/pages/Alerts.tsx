import { useEffect, useState } from 'react'
import { listAlerts } from '../api/client'
import type { AlertRead } from '../api/types'

const RULES: Record<string, string> = {
  overspeed: 'Overspeed',
  harsh_braking: 'Harsh braking',
  harsh_acceleration: 'Harsh accel',
  coolant_overheating: 'Coolant temp',
  new_dtc: 'New DTC',
  excessive_idling: 'Idle',
  fuel_drop: 'Fuel drop',
  geofence_enter: 'Geofence enter',
  geofence_exit: 'Geofence exit',
}

function fmtDate(iso: string | null) {
  return iso ? new Date(iso).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' }) : '—'
}

export default function Alerts() {
  const [alerts, setAlerts] = useState<AlertRead[]>([])
  const [stateFilter, setStateFilter] = useState<'all' | 'active' | 'cleared'>('all')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listAlerts(stateFilter === 'all' ? {} : { state: stateFilter })
      .then(setAlerts)
      .finally(() => setLoading(false))
  }, [stateFilter])

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Alerts</h1>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {(['all', 'active', 'cleared'] as const).map((s) => (
            <button
              key={s}
              className={`btn ${stateFilter === s ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => { setStateFilter(s); setLoading(true) }}
            >
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8' }}>Loading…</div>
        ) : alerts.length === 0 ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8' }}>No alerts</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Rule</th>
                <th>State</th>
                <th>Fired</th>
                <th>Cleared</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={a.id}>
                  <td>{RULES[a.rule] ?? a.rule}</td>
                  <td>
                    <span className={`badge badge-${a.state}`}>{a.state}</span>
                  </td>
                  <td style={{ fontSize: '0.8rem', color: '#64748b' }}>{fmtDate(a.fired_at)}</td>
                  <td style={{ fontSize: '0.8rem', color: '#64748b' }}>{fmtDate(a.cleared_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
