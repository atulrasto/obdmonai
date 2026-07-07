import { useEffect, useState, type FormEvent } from 'react'
import { listVehicles, listDevices, createDevice } from '../api/client'
import type { VehicleRead, DeviceRead } from '../api/types'
import FlashModal from '../components/FlashModal'

const MAIN_CPP = `// obdmonai ESP32 firmware — src/main.cpp
// 1. Fill the CONFIG block below
// 2. Paste your CA cert (infra/mosquitto/certs/ca.crt)
// 3. PlatformIO → Build (✓)  →  .pio/build/esp32dev/firmware.bin

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <mcp2515.h>
#include <TinyGPSPlus.h>
#include <Wire.h>
#include <time.h>

// ── CONFIG ────────────────────────────────────────────────────────────────────
#define DEVICE_ID   "paste-device-id-from-Devices-page"
#define CLIENT_ID   "paste-your-client-id"
#define VEHICLE_VIN "paste-vehicle-vin"
#define WIFI_SSID   "your-wifi-ssid"
#define WIFI_PASS   "your-wifi-password"
#define MQTT_HOST   "your.server.ip.or.hostname"
#define MQTT_PORT   8883
#define TOPIC       "obdmonai/" CLIENT_ID "/vehicle/" VEHICLE_VIN "/telemetry"

// CA cert — paste full contents of infra/mosquitto/certs/ca.crt
const char CA_CERT[] = R"EOF(
-----BEGIN CERTIFICATE-----
<< paste ca.crt here >>
-----END CERTIFICATE-----
)EOF";

// ── PINS ──────────────────────────────────────────────────────────────────────
#define MCP_CS    5   // MCP2515 SPI chip-select
#define GPS_RX   16   // GPS UART RX
#define GPS_TX   17   // GPS UART TX

// ── GLOBALS ───────────────────────────────────────────────────────────────────
MCP2515          can(MCP_CS);
TinyGPSPlus      gps;
HardwareSerial   gpsSerial(1);
WiFiClientSecure wifiClient;
PubSubClient     mqtt(wifiClient);
uint32_t         seq;

// ── OBD-II READ ───────────────────────────────────────────────────────────────
float obdRead(uint8_t pid) {
  struct can_frame req = {};
  req.can_id = 0x7DF; req.can_dlc = 8;
  req.data[0]=0x02; req.data[1]=0x01; req.data[2]=pid;
  can.sendMessage(&req);
  unsigned long t = millis();
  while (millis()-t < 120) {
    struct can_frame r;
    if (can.readMessage(&r)==MCP2515::ERROR_OK && r.can_id==0x7E8 && r.data[2]==pid) {
      uint8_t A=r.data[3], B=r.data[4];
      switch(pid){
        case 0x0C: return ((A<<8)|B)/4.0f;
        case 0x0D: return A;
        case 0x05: return A-40.0f;
        case 0x04: return A*100.0f/255;
        case 0x11: return A*100.0f/255;
        case 0x0F: return A-40.0f;
        case 0x2F: return A*100.0f/255;
        case 0x1F: return (float)((A<<8)|B);
      }
    }
  }
  return -1;
}

// ── MPU-6050 ─────────────────────────────────────────────────────────────────
struct Imu { float ax,ay,az,gx,gy,gz; };
Imu readImu() {
  Wire.beginTransmission(0x68); Wire.write(0x3B); Wire.endTransmission(false);
  Wire.requestFrom(0x68,14);
  auto rd=[]()->int16_t{ return (Wire.read()<<8)|Wire.read(); };
  Imu i;
  i.ax=rd()/16384.0f*9.81f; i.ay=rd()/16384.0f*9.81f; i.az=rd()/16384.0f*9.81f;
  rd(); // skip temp
  i.gx=rd()/131.0f*DEG_TO_RAD; i.gy=rd()/131.0f*DEG_TO_RAD; i.gz=rd()/131.0f*DEG_TO_RAD;
  return i;
}

// ── SETUP ─────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  gpsSerial.begin(9600,SERIAL_8N1,GPS_RX,GPS_TX);
  Wire.begin(21,22);
  Wire.beginTransmission(0x68); Wire.write(0x6B); Wire.write(0); Wire.endTransmission(); // wake MPU
  can.reset(); can.setBitrate(CAN_500KBPS,MCP_8MHZ); can.setNormalMode();
  WiFi.begin(WIFI_SSID,WIFI_PASS);
  while(WiFi.status()!=WL_CONNECTED) delay(400);
  configTime(0,0,"pool.ntp.org");
  struct tm t; while(!getLocalTime(&t)) delay(500); // wait for NTP
  seq = esp_random(); // random start — prevents duplicate-seq on reboot
  wifiClient.setCACert(CA_CERT);
  mqtt.setServer(MQTT_HOST,MQTT_PORT);
  mqtt.setBufferSize(512);
}

// ── LOOP ──────────────────────────────────────────────────────────────────────
void loop() {
  while(gpsSerial.available()) gps.encode(gpsSerial.read());
  if(!mqtt.connected()) while(!mqtt.connect("esp32-" DEVICE_ID)) delay(2000);
  mqtt.loop();

  time_t now; time(&now);
  Imu imu = readImu();

  StaticJsonDocument<512> doc;
  doc["device_id"]=DEVICE_ID; doc["ts"]=(double)now; doc["seq"]=seq++;

  JsonObject g=doc.createNestedObject("gps");
  g["lat"]=gps.location.isValid()?gps.location.lat():0;
  g["lon"]=gps.location.isValid()?gps.location.lng():0;
  g["alt"]=gps.altitude.isValid()?gps.altitude.meters():0;
  g["hdg"]=gps.course.isValid()?gps.course.deg():0;
  g["spd"]=gps.speed.isValid()?gps.speed.mps():0;

  JsonObject o=doc.createNestedObject("obd");
  o["rpm"]=obdRead(0x0C); o["speed"]=obdRead(0x0D); o["coolant"]=obdRead(0x05);
  o["load"]=obdRead(0x04); o["throttle"]=obdRead(0x11); o["intake_temp"]=obdRead(0x0F);
  o["fuel_level"]=obdRead(0x2F); o["run_time"]=obdRead(0x1F);

  JsonObject im=doc.createNestedObject("imu");
  im["ax"]=imu.ax; im["ay"]=imu.ay; im["az"]=imu.az;
  im["gx"]=imu.gx; im["gy"]=imu.gy; im["gz"]=imu.gz;

  doc.createNestedArray("dtc");
  doc["ign"]=(obdRead(0x0C)>0);

  char buf[512]; serializeJson(doc,buf,sizeof(buf));
  mqtt.publish(TOPIC,buf);
  delay(2000);
}`

const OBD_PIDS = [
  { param: 'Engine RPM',        pid: '0x0C', unit: 'rpm',     field: 'obd.rpm'          },
  { param: 'Vehicle speed',     pid: '0x0D', unit: 'km/h',    field: 'obd.speed'        },
  { param: 'Coolant temp',      pid: '0x05', unit: '°C − 40', field: 'obd.coolant'      },
  { param: 'Engine load',       pid: '0x04', unit: '%',        field: 'obd.load'         },
  { param: 'Throttle position', pid: '0x11', unit: '%',        field: 'obd.throttle'     },
  { param: 'Intake air temp',   pid: '0x0F', unit: '°C − 40', field: 'obd.intake_temp'  },
  { param: 'Fuel level',        pid: '0x2F', unit: '%',        field: 'obd.fuel_level'   },
  { param: 'Run time since start', pid: '0x1F', unit: 'seconds', field: 'obd.run_time'  },
]

const PAYLOAD_EXAMPLE = `{
  "device_id": "<UUID from Device ID column>",
  "ts": 1735000000.0,
  "seq": 42,
  "gps": {
    "lat": 18.5204, "lon": 73.8567,
    "alt": 411.0,   "hdg": 90.0,   "spd": 18.0
  },
  "obd": {
    "rpm": 2200,     "speed": 65,   "coolant": 88,
    "load": 30,      "throttle": 22,"intake_temp": 35,
    "fuel_level": 72,"run_time": 3600
  },
  "imu": {
    "ax": 0.1, "ay": 0.0, "az": 9.81,
    "gx": 0.0, "gy": 0.0, "gz": 0.0
  },
  "dtc": ["P0420"],
  "ign": true
}`

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      className="btn btn-secondary"
      style={{ padding: '0.15rem 0.45rem', fontSize: '0.7rem', marginLeft: '0.4rem' }}
      onClick={() => {
        navigator.clipboard.writeText(text)
        setCopied(true)
        setTimeout(() => setCopied(false), 1500)
      }}
    >
      {copied ? '✓' : 'copy'}
    </button>
  )
}

export default function Devices() {
  const [vehicles, setVehicles] = useState<VehicleRead[]>([])
  const [devices, setDevices] = useState<DeviceRead[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [showGuide, setShowGuide] = useState(false)
  const [vehicleId, setVehicleId] = useState('')
  const [serial, setSerial] = useState('')
  const [firmware, setFirmware] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [flashDevice, setFlashDevice] = useState<DeviceRead | null>(null)

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
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            className="btn btn-secondary"
            onClick={() => setShowGuide(!showGuide)}
          >
            {showGuide ? 'Hide' : 'ESP32 Firmware Guide'}
          </button>
          <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
            {showForm ? 'Cancel' : '+ Add device'}
          </button>
        </div>
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
                <th>Device ID (put in firmware)</th>
                <th>Vehicle</th>
                <th>Firmware</th>
                <th>Provisioned</th>
                <th>Flash</th>
              </tr>
            </thead>
            <tbody>
              {devices.map((d) => {
                const v = vehicleMap.get(d.vehicle_id)
                return (
                  <tr key={d.id}>
                    <td style={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>{d.serial}</td>
                    <td style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#475569' }}>
                      {d.id}
                      <CopyButton text={d.id} />
                    </td>
                    <td>{v ? `${v.make} ${v.model_name} (${v.vin})` : '—'}</td>
                    <td>{d.firmware_version ?? '—'}</td>
                    <td style={{ fontSize: '0.8rem', color: '#64748b' }}>
                      {d.provisioned_at ? new Date(d.provisioned_at).toLocaleDateString() : '—'}
                    </td>
                    <td>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: '0.2rem 0.6rem', fontSize: '0.78rem' }}
                        onClick={() => setFlashDevice(d)}
                        title="Flash firmware via Web Serial (Chrome/Edge only)"
                      >
                        ⚡ Flash
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* ── Flash modal ─────────────────────────────────────────────────────── */}
      {flashDevice && (
        <FlashModal
          deviceId={flashDevice.id}
          deviceSerial={flashDevice.serial}
          onClose={() => setFlashDevice(null)}
        />
      )}

      {/* ── ESP32 Firmware Guide ─────────────────────────────────────────────── */}
      {showGuide && (
        <div className="card" style={{ marginTop: '1.5rem' }}>
          <h2 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '1.25rem', color: '#0f172a' }}>
            ESP32 Firmware Guide
          </h2>

          {/* MQTT connection */}
          <section style={{ marginBottom: '1.5rem' }}>
            <h3 style={{ fontSize: '0.82rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#64748b', marginBottom: '0.75rem' }}>
              1 — MQTT Connection
            </h3>
            <table className="table" style={{ fontSize: '0.83rem' }}>
              <thead><tr><th>Setting</th><th>Value</th></tr></thead>
              <tbody>
                <tr><td>Broker host</td><td style={{ fontFamily: 'monospace' }}>your-server-ip-or-domain</td></tr>
                <tr><td>Port</td><td style={{ fontFamily: 'monospace' }}>8883 (TLS/SSL)</td></tr>
                <tr><td>CA certificate</td><td style={{ fontFamily: 'monospace' }}>infra/mosquitto/certs/ca.crt</td></tr>
                <tr><td>Client cert</td><td style={{ fontFamily: 'monospace' }}>generate per-device</td></tr>
                <tr><td>Topic</td><td style={{ fontFamily: 'monospace' }}>obdmonai/{'{'}client_id{'}'}/vehicle/{'{'}vin{'}'}/telemetry</td></tr>
                <tr><td>Publish interval</td><td>2 seconds</td></tr>
                <tr><td>Payload format</td><td>JSON (or CBOR for smaller packets)</td></tr>
              </tbody>
            </table>
          </section>

          {/* OBD-II PID table */}
          <section style={{ marginBottom: '1.5rem' }}>
            <h3 style={{ fontSize: '0.82rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#64748b', marginBottom: '0.75rem' }}>
              2 — OBD-II CAN Bus PIDs to Read
            </h3>
            <p style={{ fontSize: '0.8rem', color: '#64748b', marginBottom: '0.75rem' }}>
              Use Mode 01 (current data) PID requests over the OBD-II port (CAN 11-bit, 500 kbps).
              Connect via MCP2515 + SN65HVD230 to the OBD-II 16-pin connector (pin 6 = CAN-H, pin 14 = CAN-L).
            </p>
            <table className="table" style={{ fontSize: '0.83rem' }}>
              <thead>
                <tr>
                  <th>Parameter</th>
                  <th>PID (Mode 01)</th>
                  <th>Unit / Formula</th>
                  <th>JSON field</th>
                </tr>
              </thead>
              <tbody>
                {OBD_PIDS.map((row) => (
                  <tr key={row.pid}>
                    <td>{row.param}</td>
                    <td style={{ fontFamily: 'monospace', fontWeight: 600 }}>{row.pid}</td>
                    <td>{row.unit}</td>
                    <td style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#475569' }}>{row.field}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: '0.5rem' }}>
              Coolant & intake temp: raw byte − 40 = °C.  Fuel level: byte × 100 / 255 = %.  Engine load: byte × 100 / 255 = %.
            </p>
          </section>

          {/* GPS + IMU */}
          <section style={{ marginBottom: '1.5rem' }}>
            <h3 style={{ fontSize: '0.82rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#64748b', marginBottom: '0.75rem' }}>
              3 — GPS &amp; IMU
            </h3>
            <table className="table" style={{ fontSize: '0.83rem' }}>
              <thead><tr><th>Sensor</th><th>Module</th><th>Interface</th><th>Fields</th></tr></thead>
              <tbody>
                <tr>
                  <td>GPS</td>
                  <td>Neo-6M / L76K</td>
                  <td>UART (NMEA)</td>
                  <td style={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>gps.lat, gps.lon, gps.alt, gps.hdg, gps.spd</td>
                </tr>
                <tr>
                  <td>IMU</td>
                  <td>MPU-6050 / ICM-42688</td>
                  <td>I²C</td>
                  <td style={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>imu.ax/ay/az (m/s²), imu.gx/gy/gz (rad/s)</td>
                </tr>
              </tbody>
            </table>
          </section>

          {/* Payload schema */}
          <section style={{ marginBottom: '1.25rem' }}>
            <h3 style={{ fontSize: '0.82rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#64748b', marginBottom: '0.75rem' }}>
              4 — Full JSON Payload Schema
            </h3>
            <div style={{ position: 'relative' }}>
              <pre style={{
                background: '#0f172a', color: '#e2e8f0', padding: '1rem 1.25rem',
                borderRadius: '0.5rem', fontSize: '0.76rem', lineHeight: 1.6,
                overflowX: 'auto', margin: 0,
              }}>
                {PAYLOAD_EXAMPLE}
              </pre>
              <CopyButton text={PAYLOAD_EXAMPLE} />
            </div>
            <p style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: '0.5rem' }}>
              <strong>device_id</strong> — copy from the Device ID column in the table above.<br />
              <strong>ts</strong> — Unix epoch seconds (float), device-side timestamp (not server arrival time).<br />
              <strong>seq</strong> — monotonically increasing counter per device; duplicates are silently ignored.<br />
              <strong>dtc</strong> — array of active fault codes, e.g. <code>["P0420"]</code>; empty array if none.
            </p>
          </section>

          {/* PlatformIO snippet */}
          <section>
            <h3 style={{ fontSize: '0.82rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#64748b', marginBottom: '0.75rem' }}>
              5 — PlatformIO Quick-Start
            </h3>
            <pre style={{
              background: '#0f172a', color: '#e2e8f0', padding: '1rem 1.25rem',
              borderRadius: '0.5rem', fontSize: '0.76rem', lineHeight: 1.6,
              overflowX: 'auto', margin: 0,
            }}>
{`; platformio.ini
[env:esp32dev]
platform  = espressif32
board     = esp32dev
framework = arduino
lib_deps  =
  knolleary/PubSubClient @ ^2.8
  bblanchon/ArduinoJson  @ ^7
  mcp2515/mcp2515        @ ^1.0.2   ; CAN bus (MCP2515 SPI)
  mikalhart/TinyGPSPlus  @ ^1.0.3   ; GPS NMEA
  ; Wire is built-in (MPU-6050 I2C)`}
            </pre>
          </section>

          {/* main.cpp template */}
          <section style={{ marginBottom: '1.25rem' }}>
            <h3 style={{ fontSize: '0.82rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#64748b', marginBottom: '0.75rem' }}>
              6 — Complete src/main.cpp
            </h3>
            <p style={{ fontSize: '0.78rem', color: '#64748b', marginBottom: '0.6rem' }}>
              Copy this into <code>src/main.cpp</code> in your PlatformIO project. Fill in the CONFIG block at the top.
              Copy the Device ID from the table above and the CA cert from <code>infra/mosquitto/certs/ca.crt</code>.
            </p>
            <div style={{ position: 'relative' }}>
              <pre style={{
                background: '#0f172a', color: '#e2e8f0', padding: '1rem 1.25rem',
                borderRadius: '0.5rem', fontSize: '0.72rem', lineHeight: 1.55,
                overflowX: 'auto', margin: 0, maxHeight: 420, overflowY: 'auto',
              }}>
                {MAIN_CPP}
              </pre>
              <div style={{ position: 'absolute', top: '0.5rem', right: '0.5rem' }}>
                <CopyButton text={MAIN_CPP} />
              </div>
            </div>
          </section>

          {/* Build steps */}
          <section>
            <h3 style={{ fontSize: '0.82rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#64748b', marginBottom: '0.75rem' }}>
              7 — Build &amp; Flash workflow
            </h3>
            <ol style={{ fontSize: '0.82rem', color: '#334155', lineHeight: 2, paddingLeft: '1.25rem', margin: 0 }}>
              <li>Install <strong>VS Code</strong> + <strong>PlatformIO IDE</strong> extension.</li>
              <li>PlatformIO Home → <em>New Project</em> → Board: <code>ESP32 Dev Module</code> → Framework: Arduino.</li>
              <li>Replace <code>platformio.ini</code> with the snippet in section 5.</li>
              <li>Replace <code>src/main.cpp</code> with the template in section 6.</li>
              <li>Fill in the <code>CONFIG</code> block: Device ID (copy from table above), WiFi credentials, MQTT host.</li>
              <li>Paste the contents of <code>infra/mosquitto/certs/ca.crt</code> into the <code>CA_CERT</code> string.</li>
              <li>Click <strong>Build</strong> (✓ icon in the bottom toolbar) or press <kbd>Ctrl+Alt+B</kbd>.</li>
              <li>
                Firmware binary is created at:<br />
                <code style={{ background: '#f1f5f9', padding: '0.1rem 0.35rem', borderRadius: 4 }}>
                  .pio/build/esp32dev/firmware.bin
                </code>
              </li>
              <li>Plug the ESP32 into this computer via USB, then click <strong>⚡ Flash</strong> in the table above.</li>
              <li>Select the firmware.bin file → <em>Connect &amp; Flash</em> → done.</li>
            </ol>
            <p style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: '0.75rem' }}>
              First flash also programs the bootloader and partition table — use PlatformIO's built-in <em>Upload</em> button for that.
              Subsequent OTA updates (app only) can be done from this browser using the ⚡ Flash button at 0x10000.
            </p>
          </section>
        </div>
      )}
    </div>
  )
}
