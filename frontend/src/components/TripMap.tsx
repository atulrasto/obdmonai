import { useEffect, useRef } from 'react'
import type { TripPointRead } from '../api/types'
// maplibre-gl is aliased to a no-op stub in vitest; real import in production
import { Map, NavigationControl } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

interface Props {
  points: TripPointRead[]
  height?: number
}

// Default public tile style — swap VITE_MAP_STYLE env var for production key
const MAP_STYLE =
  (import.meta.env.VITE_MAP_STYLE as string | undefined) ??
  'https://demotiles.maplibre.org/style.json'

export default function TripMap({ points, height = 400 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<InstanceType<typeof Map> | null>(null)

  const validPoints = points.filter((p) => p.lat != null && p.lon != null)

  useEffect(() => {
    if (!containerRef.current || validPoints.length === 0) return

    const first = validPoints[0]
    const map = new Map({
      container: containerRef.current,
      style: MAP_STYLE,
      center: [first.lon!, first.lat!],
      zoom: 13,
    })
    mapRef.current = map
    map.addControl(new NavigationControl())

    const coords = validPoints.map((p) => [p.lon!, p.lat!])

    map.on('load', () => {
      map.addSource('route', {
        type: 'geojson',
        data: {
          type: 'Feature',
          properties: {},
          geometry: { type: 'LineString', coordinates: coords },
        },
      })
      map.addLayer({
        id: 'route',
        type: 'line',
        source: 'route',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': '#3b82f6', 'line-width': 4 },
      })

      // Zoom to fit
      const lons = coords.map((c) => c[0])
      const lats = coords.map((c) => c[1])
      map.fitBounds(
        [
          [Math.min(...lons), Math.min(...lats)],
          [Math.max(...lons), Math.max(...lats)],
        ],
        { padding: 40 },
      )
    })

    return () => {
      mapRef.current?.remove()
      mapRef.current = null
    }
  }, [validPoints.length]) // eslint-disable-line react-hooks/exhaustive-deps

  if (validPoints.length === 0) {
    return (
      <div
        style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f8fafc', borderRadius: 8, color: '#94a3b8' }}
      >
        No GPS data for this trip
      </div>
    )
  }

  return <div ref={containerRef} style={{ height, borderRadius: 8 }} data-testid="trip-map" />
}
