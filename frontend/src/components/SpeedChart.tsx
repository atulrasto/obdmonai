import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { TripPointRead } from '../api/types'

interface Props {
  points: TripPointRead[]
  title?: string
}

interface ChartRow {
  time: string
  speed: number | null
  rpm: number | null
}

function fmtTime(isoStr: string): string {
  return new Date(isoStr).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function SpeedChart({ points, title = 'Speed & RPM' }: Props) {
  const data: ChartRow[] = points.map((p) => ({
    time: fmtTime(p.ts),
    speed: p.obd_speed ?? null,
    rpm: p.obd_rpm != null ? Math.round(p.obd_rpm / 10) : null, // scale rpm/10 for dual axis
  }))

  return (
    <div className="card" style={{ marginBottom: '1rem' }}>
      <h3 style={{ marginBottom: '1rem', fontSize: '0.9rem', color: '#475569' }}>{title}</h3>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="time" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
          <YAxis yAxisId="left" tick={{ fontSize: 11 }} label={{ value: 'km/h', angle: -90, position: 'insideLeft', fontSize: 11 }} />
          <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} label={{ value: 'RPM ÷10', angle: 90, position: 'insideRight', fontSize: 11 }} />
          <Tooltip />
          <Legend />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="speed"
            name="Speed (km/h)"
            stroke="#3b82f6"
            dot={false}
            strokeWidth={2}
          />
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="rpm"
            name="RPM ÷10"
            stroke="#f59e0b"
            dot={false}
            strokeWidth={1.5}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
