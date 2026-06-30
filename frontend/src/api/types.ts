// API response types — derived from backend Pydantic schemas.
// Re-generate at any time with: npm run gen-api

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface ClientRead {
  id: string
  name: string
  slug: string
  created_at: string
}

export interface VehicleRead {
  id: string
  client_id: string
  vin: string
  make: string
  model_name: string
  year: number
  created_at: string
}

export interface DeviceRead {
  id: string
  vehicle_id: string
  client_id: string
  serial: string
  firmware_version: string | null
  provisioned_at: string | null
}

export interface AlertRead {
  id: string
  vehicle_id: string
  device_id: string | null
  rule: string
  state: 'active' | 'cleared'
  created_at: string
  fired_at: string | null
  cleared_at: string | null
}

export interface GeofenceRead {
  id: string
  vehicle_id: string
  client_id: string
  name: string
  lat: number
  lon: number
  radius_m: number
  active: boolean
  created_at: string
}

export interface VehicleKPIRead {
  vehicle_id: string
  from_ts: string
  to_ts: string
  reading_count: number
  distance_km: number
  drive_time_sec: number
  idle_time_sec: number
  harsh_events: number
  avg_speed: number | null
  max_speed: number | null
}

export interface TripRead {
  trip_id: number
  vehicle_id: string
  started_at: string
  ended_at: string
  point_count: number
  distance_km: number
  drive_time_sec: number
  avg_speed: number | null
  max_speed: number | null
}

export interface TripPointRead {
  ts: string
  lat: number | null
  lon: number | null
  obd_speed: number | null
  obd_rpm: number | null
  obd_coolant: number | null
  ign: boolean | null
}

export interface FleetVehicleRead {
  vehicle_id: string
  reading_count: number
  distance_km: number
  last_seen: string | null
  avg_speed: number | null
}

export interface DriverScoreResponse {
  vehicle_id: string
  score: number | null
  window_hours: number
  computed_at: string
}

export interface MaintenanceResponse {
  vehicle_id: string
  is_anomaly: boolean | null
  anomaly_score: number | null
  window_hours: number
  computed_at: string
}

export interface SummaryResponse {
  vehicle_id: string
  summary: string
  computed_at: string
}

export interface VehicleCreateRequest {
  vin: string
  make: string
  model_name: string
  year: number
}

export interface DeviceCreateRequest {
  vehicle_id: string
  serial: string
  firmware_version?: string
}

export interface GeofenceCreateRequest {
  vehicle_id: string
  name: string
  lat: number
  lon: number
  radius_m: number
}
