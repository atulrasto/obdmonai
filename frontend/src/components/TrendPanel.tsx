import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  CartesianGrid, Line, LineChart, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { getParamTrend } from '../api/client'
import type { TrendPoint } from '../api/types'

// ── Parameter metadata ────────────────────────────────────────────────────────

export interface ParamMeta {
  label: string
  unit: string
  color: string
  pid: string
  refLines?: { value: number; label: string; color: string }[]
}

export const PARAM_META: Record<string, ParamMeta> = {
  obd_rpm:         { label: 'Engine RPM',      unit: 'rpm',  color: '#6366f1', pid: '0x0C',
                     refLines: [{ value: 4500, label: 'Redline', color: '#dc2626' }] },
  obd_speed:       { label: 'Vehicle Speed',   unit: 'km/h', color: '#0ea5e9', pid: '0x0D',
                     refLines: [{ value: 80, label: '80 km/h', color: '#f59e0b' }] },
  obd_coolant:     { label: 'Coolant Temp',    unit: '°C',   color: '#10b981', pid: '0x05',
                     refLines: [
                       { value: 80,  label: 'Normal',    color: '#16a34a' },
                       { value: 100, label: 'Overtemp',  color: '#dc2626' },
                     ] },
  obd_load:        { label: 'Engine Load',     unit: '%',    color: '#f59e0b', pid: '0x04',
                     refLines: [{ value: 80, label: 'High', color: '#dc2626' }] },
  obd_throttle:    { label: 'Throttle Pos',    unit: '%',    color: '#10b981', pid: '0x11' },
  obd_intake_temp: { label: 'Intake Air Temp', unit: '°C',   color: '#8b5cf6', pid: '0x0F' },
  obd_fuel_level:  { label: 'Fuel Level',      unit: '%',    color: '#16a34a', pid: '0x2F',
                     refLines: [{ value: 15, label: 'Low', color: '#dc2626' }] },
  obd_run_time:    { label: 'Engine Run Time', unit: 'min',  color: '#64748b', pid: '0x1F' },
}

// ── Period config ─────────────────────────────────────────────────────────────

type PeriodKey = '5min' | '15min' | '30min' | '1hour' | 'daily' | 'weekly' | 'monthly' | 'custom'

interface PeriodDef {
  key: PeriodKey
  label: string
  group: 'short' | 'long' | 'custom'
}

const PERIODS: PeriodDef[] = [
  { key: '5min',    label: '5 min',       group: 'short' },
  { key: '15min',   label: '15 min',      group: 'short' },
  { key: '30min',   label: '30 min',      group: 'short' },
  { key: '1hour',   label: '1 hr',        group: 'short' },
  { key: 'daily',   label: 'Daily (24h)', group: 'long'  },
  { key: 'weekly',  label: 'Weekly (7d)', group: 'long'  },
  { key: 'monthly', label: 'Monthly (30d)', group: 'long' },
  { key: 'custom',  label: 'Custom',      group: 'custom' },
]

function pad2(n: number) { return n.toString().padStart(2, '0') }

function fmtLabel(ts: string, period: PeriodKey, customMin: number) {
  const d = new Date(ts)
  const hh = pad2(d.getHours()), mm = pad2(d.getMinutes()), ss = pad2(d.getSeconds())
  if (period === '5min' || period === '15min' || period === '30min' ||
      (period === 'custom' && customMin <= 30)) {
    return `${hh}:${mm}:${ss}`
  }
  if (period === '1hour' || period === 'daily' ||
      (period === 'custom' && customMin <= 120)) {
    return `${hh}:${mm}`
  }
  if (period === 'weekly' || (period === 'custom' && customMin <= 2880)) {
    return d.toLocaleDateString([], { weekday: 'short' }) + ` ${hh}:${mm}`
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  vehicleId: string
  param: string
  onClose: () => void
}

export default function TrendPanel({ vehicleId, param, onClose }: Props) {
  const [period, setPeriod]       = useState<PeriodKey>('5min')
  const [customMin, setCustomMin] = useState(10)
  const [hrInput, setHrInput]     = useState('0')
  const [minInput, setMinInput]   = useState('10')
  const [data, setData]           = useState<TrendPoint[]>([])
  const [loading, setLoading]     = useState(true)
  const abortRef = useRef<AbortController | null>(null)

  const meta = PARAM_META[param]

  useEffect(() => {
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    setLoading(true)

    const mins = period === 'custom' ? customMin : undefined
    getParamTrend(vehicleId, param, period, mins)
      .then((pts) => setData(pts))
      .catch(() => setData([]))
      .finally(() => setLoading(false))
  }, [vehicleId, param, period, customMin])

  // Convert run_time seconds → minutes for display
  const chartData = data.map((p) => ({
    ts: fmtLabel(p.ts, period, customMin),
    value: p.value != null
      ? (param === 'obd_run_time' ? +(p.value / 60).toFixed(1) : +p.value.toFixed(2))
      : null,
  }))

  const values = chartData.map((d) => d.value).filter((v): v is number => v != null)
  const minVal  = values.length ? Math.min(...values) : 0
  const maxVal  = values.length ? Math.max(...values) : 100
  const pad     = (maxVal - minVal) * 0.15 || 5
  const yMin    = Math.max(0, Math.floor(minVal - pad))
  const yMax    = Math.ceil(maxVal + pad)

  function applyCustom(e: FormEvent) {
    e.preventDefault()
    const h = parseInt(hrInput, 10) || 0
    const m = parseInt(minInput, 10) || 0
    const total = h * 60 + m
    if (total >= 1 && total <= 10080) { setCustomMin(total); setPeriod('custom') }
  }

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="card" style={{ marginBottom: '1.5rem', border: `2px solid ${meta.color}30`, boxShadow: '0 4px 20px rgba(0,0,0,0.06)' }}>

      {/* header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.875rem' }}>
        <div>
          <span style={{ fontWeight: 700, fontSize: '1rem', color: '#0f172a' }}>{meta.label}</span>
          <span style={{ marginLeft: '0.5rem', fontSize: '0.72rem', fontFamily: 'monospace', color: '#94a3b8' }}>{meta.pid}</span>
          <span style={{ marginLeft: '0.4rem', fontSize: '0.75rem', color: '#64748b' }}>/ {meta.unit}</span>
        </div>
        <button onClick={onClose}
          style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1rem', color: '#94a3b8', lineHeight: 1, padding: '0.2rem 0.4rem' }}>
          ✕
        </button>
      </div>

      {/* ── period buttons — two rows ── */}
      <div style={{ marginBottom: '0.75rem' }}>
        {/* short periods */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', marginBottom: '0.4rem' }}>
          {PERIODS.filter((p) => p.group === 'short').map(({ key, label }) => (
            <PeriodBtn key={key} label={label} active={period === key} color={meta.color}
              onClick={() => setPeriod(key)} />
          ))}
          {/* custom inline: Last [hr] hr [min] min Go */}
          <form onSubmit={applyCustom} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', flexWrap: 'wrap' }}>
            <PeriodBtn label="Last" active={period === 'custom'} color={meta.color}
              onClick={() => setPeriod('custom')} />
            <input
              type="number" min={0} max={168}
              value={hrInput}
              onChange={(e) => setHrInput(e.target.value)}
              onFocus={() => setPeriod('custom')}
              placeholder="0"
              style={{
                width: 44, padding: '0.28rem 0.3rem', borderRadius: 6, border: '1.5px solid #e2e8f0',
                fontSize: '0.78rem', textAlign: 'center', fontWeight: 500, outline: 'none',
              }}
            />
            <span style={{ fontSize: '0.78rem', color: '#64748b' }}>hr</span>
            <input
              type="number" min={0} max={59}
              value={minInput}
              onChange={(e) => setMinInput(e.target.value)}
              onFocus={() => setPeriod('custom')}
              placeholder="10"
              style={{
                width: 44, padding: '0.28rem 0.3rem', borderRadius: 6, border: '1.5px solid #e2e8f0',
                fontSize: '0.78rem', textAlign: 'center', fontWeight: 500, outline: 'none',
              }}
            />
            <span style={{ fontSize: '0.78rem', color: '#64748b' }}>min</span>
            <button type="submit" style={{
              padding: '0.28rem 0.55rem', borderRadius: 6, border: `1.5px solid ${meta.color}`,
              background: meta.color, color: '#fff', fontSize: '0.72rem', fontWeight: 600, cursor: 'pointer',
            }}>Go</button>
          </form>
        </div>
        {/* long periods */}
        <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
          {PERIODS.filter((p) => p.group === 'long').map(({ key, label }) => (
            <PeriodBtn key={key} label={label} active={period === key} color={meta.color}
              onClick={() => setPeriod(key)} />
          ))}
        </div>
      </div>

      {/* ── chart area ── */}
      {loading ? (
        <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>
          Loading…
        </div>
      ) : chartData.length < 2 ? (
        <div style={{ height: 260, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
          <div style={{ fontSize: '2rem' }}>{chartData.length === 1 ? '⏳' : '📡'}</div>
          {chartData.length === 1 && (
            <div style={{ fontWeight: 700, fontSize: '1.1rem', color: '#0f172a' }}>
              {chartData[0].value} {meta.unit}
            </div>
          )}
          <div style={{ fontSize: '0.8rem', color: '#64748b', textAlign: 'center' }}>
            {chartData.length === 0
              ? 'No data — start the simulator or pick a longer window'
              : 'Only 1 reading in this window — extend the time range or keep running'}
          </div>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis
              dataKey="ts"
              tick={{ fontSize: 9 }}
              angle={-30}
              textAnchor="end"
              height={36}
              interval={Math.max(0, Math.floor(chartData.length / 8) - 1)}
            />
            <YAxis
              domain={[yMin, yMax]}
              tick={{ fontSize: 10 }}
              width={45}
              label={{ value: meta.unit, angle: -90, position: 'insideLeft', fontSize: 10, fill: '#94a3b8' }}
            />
            <Tooltip
              formatter={(val: number) => [`${val} ${meta.unit}`, meta.label]}
              labelStyle={{ fontSize: 11 }}
              contentStyle={{ fontSize: 11, borderRadius: 6, border: '1px solid #e2e8f0' }}
            />
            {(meta.refLines ?? []).map((rl) => (
              <ReferenceLine key={rl.value} y={rl.value} stroke={rl.color} strokeDasharray="4 3"
                label={{ value: rl.label, fill: rl.color, fontSize: 10, position: 'insideTopRight' }}
              />
            ))}
            <Line
              type="monotone"
              dataKey="value"
              name={meta.label}
              stroke={meta.color}
              strokeWidth={2}
              dot={chartData.length <= 60 ? { r: 3, fill: meta.color } : false}
              activeDot={{ r: 5 }}
              connectNulls={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}

      {/* stats row */}
      {values.length > 0 && (
        <div style={{ display: 'flex', gap: '2rem', marginTop: '0.75rem', fontSize: '0.78rem', color: '#64748b', flexWrap: 'wrap' }}>
          <span>Min: <strong style={{ color: '#0f172a' }}>{Math.min(...values).toFixed(1)} {meta.unit}</strong></span>
          <span>Avg: <strong style={{ color: '#0f172a' }}>{(values.reduce((a, b) => a + b, 0) / values.length).toFixed(1)} {meta.unit}</strong></span>
          <span>Max: <strong style={{ color: '#0f172a' }}>{Math.max(...values).toFixed(1)} {meta.unit}</strong></span>
          <span style={{ marginLeft: 'auto', color: '#94a3b8' }}>{values.length} points</span>
        </div>
      )}
    </div>
  )
}

// ── Pill button ───────────────────────────────────────────────────────────────
function PeriodBtn({ label, active, color, onClick }: {
  label: string; active: boolean; color: string; onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: '0.28rem 0.75rem', borderRadius: 6, fontSize: '0.78rem', cursor: 'pointer', fontWeight: 500,
        border: `1.5px solid ${active ? color : '#e2e8f0'}`,
        background: active ? color : '#fff',
        color: active ? '#fff' : '#475569',
        transition: 'all 0.12s',
        whiteSpace: 'nowrap',
      }}
    >
      {label}
    </button>
  )
}
