# obdmonai — OBU Firmware (ESP32-WROOM-32)

On-board unit firmware for the obdmonai fleet monitoring system.
Reads OBD-II data via CAN bus (TWAI), GPS via UART, IMU via I2C,
encodes each reading as CBOR, and publishes to the cloud backend
over MQTT/TLS. Stores frames locally on SD card when offline
(store-and-forward ring buffer).

---

## Hardware

### Bill of materials

| Qty | Part                          | Purpose                           |
|-----|-------------------------------|-----------------------------------|
| 1   | ESP32-WROOM-32 dev board      | MCU / WiFi                        |
| 1   | SN65HVD230 CAN transceiver    | CAN-H / CAN-L level shifting      |
| 1   | NEO-6M (or compatible)        | GPS/GNSS (UART, 9600 baud)        |
| 1   | MPU-6050 breakout             | 3-axis accelerometer + gyroscope  |
| 1   | MicroSD breakout (SPI)        | Store-and-forward ring buffer     |
| 1   | OBD-II J1962 cable / adapter  | Vehicle CAN bus access            |
| 1   | 12 V → 3.3 V regulator        | Power from OBD-II pin 16 (VBATT) |
| 1   | Voltage divider (10 kΩ / 3 kΩ) | Ignition sense (12 V → 3.3 V)   |

---

## Wiring / Pinout

### CAN bus (TWAI) — OBD-II via SN65HVD230

```
ESP32-WROOM-32           SN65HVD230             OBD-II J1962
─────────────────────────────────────────────────────────────
GPIO5  (TX)  ──────────  TXD
GPIO4  (RX)  ──────────  RXD
3.3 V        ──────────  VCC / Rs (Rs → GND via 10 kΩ for slope control)
GND          ──────────  GND
                         CANH  ──────────────── pin 6  (CAN-H)
                         CANL  ──────────────── pin 14 (CAN-L)
```

> The OBD-II port provides HS-CAN at 500 kbit/s on pins 6 & 14 for most
> OBD-II compliant vehicles (ISO 15765-4 / SAE J1939).
> Some older vehicles may use KW2000 on pin 7 — not supported.

### GNSS — NEO-6M (UART2)

```
ESP32        NEO-6M
───────────────────
GPIO17 (TX)  RXD
GPIO16 (RX)  TXD
3.3 V        VCC
GND          GND
```

### IMU — MPU-6050 (I2C)

```
ESP32        MPU-6050
──────────────────────
GPIO21 (SDA) SDA
GPIO22 (SCL) SCL
3.3 V        VCC
GND          GND
              AD0 → GND (I2C address 0x68)
```

### SD card — SPI

```
ESP32        MicroSD breakout
─────────────────────────────
GPIO15 (CS)  CS
GPIO23 (MOSI) MOSI / DI
GPIO19 (MISO) MISO / DO
GPIO18 (SCK) CLK
3.3 V        VCC (use LDO if card requires 3.3 V strictly)
GND          GND
```

### Ignition sense

```
OBD-II pin 16 (VBATT, ~12 V) ──┬──  10 kΩ  ──┬── GPIO34
                                │              │
                               GND           3 kΩ
                                              │
                                             GND
```
Voltage divider gives ≈ 3.0 V on GPIO34 when ignition is on (< 3.3 V max).
GPIO34 is input-only; no internal pull-up.

### Power

```
OBD-II pin 16 (VBATT 9–16 V) → DC-DC 3.3 V → ESP32 3V3 pin
OBD-II pin 4  (Chassis GND)  → GND
```

---

## Build

Install [PlatformIO Core](https://docs.platformio.org/page/core/installation.html), then:

```bash
cd firmware/obu-esp32
pio run -e esp32dev          # compile
pio run -e esp32dev -t upload  # flash (device must be connected via USB)
pio device monitor           # serial console (115200 baud)
```

---

## Provisioning

Each unit must be provisioned before first use.  There is no over-the-air
provisioning path — all identity material is written once and stored in
NVS + LittleFS inside the ESP32's own flash.

### 1. Write NVS keys (via USB serial + Arduino sketch or `esptool`)

Using the Arduino `Preferences` API at boot (one-time setup sketch):

```cpp
#include <Preferences.h>
Preferences p;
p.begin("obdmonai", false);
p.putString("device_id",  "<UUID from /devices POST response>");
p.putString("client_id",  "<tenant UUID>");
p.putString("vin",        "ACME01VOLVO0FH1600");
p.putString("wifi_ssid",  "FleetWifi");
p.putString("wifi_pass",  "s3cr3t");
p.putString("mqtt_host",  "fleet.example.com");
p.end();
```

### 2. Upload TLS certificates to LittleFS

Generate device cert via `infra/mosquitto/gen-certs.sh` (produces
`certs/<serial>.crt` + `certs/<serial>.key`).  **Never commit `.key` files.**

Upload to unit:
```bash
# Create data/certs/ directory in obu-esp32/
mkdir -p data/certs
cp infra/mosquitto/certs/ca.crt          data/certs/ca.pem
cp infra/mosquitto/certs/<serial>.crt    data/certs/device.crt
cp infra/mosquitto/certs/<serial>.key    data/certs/device.key

# Build and upload LittleFS image
pio run -e esp32dev --target buildfs
pio run -e esp32dev --target uploadfs
```

### 3. Register the device in the backend

```bash
curl -X POST http://localhost:8002/devices \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "vehicle_id": "<vehicle-uuid>",
    "serial": "<OBU-serial>",
    "firmware_version": "1.0.0"
  }'
```
Note the returned `id` — that is the `device_id` to write to NVS.

---

## CBOR payload format

The firmware encodes each reading as a CBOR map matching the backend's
`TelemetryPayload` Pydantic schema (see `backend/app/ingest/schemas.py`):

```
{
  "device_id": "<UUID string>",
  "ts":        <Unix epoch integer>,
  "seq":       <uint>,
  "gps":       { "lat": f32, "lon": f32, "alt": f32, "hdg": f32, "spd": f32 },
  "obd":       { "speed": f32, "rpm": f32, "coolant": f32, "fuel_level": f32,
                 "load": f32, "throttle": f32, "intake_temp": f32, "run_time": uint },
  "imu":       { "ax": f32, "ay": f32, "az": f32, "gx": f32, "gy": f32, "gz": f32 },
  "dtc":       ["P0300", ...],
  "ign":       true / false
}
```

Floats are encoded as CBOR float32 (major type 7, additional info 26, 4 bytes).
The Python `cbor2` library decodes them to Python floats transparently.

Schema compatibility is verified by the host-side test:
```bash
pytest backend/tests/test_phase11_firmware.py -v
```

---

## OBD-II PIDs polled (every 10 s)

| PID  | Description                  | Formula          | Unit  |
|------|------------------------------|------------------|-------|
| 0x0C | Engine RPM                   | (A×256+B)/4      | rpm   |
| 0x0D | Vehicle speed                | A                | km/h  |
| 0x05 | Coolant temperature          | A − 40           | °C    |
| 0x2F | Fuel tank level              | A × 100/255      | %     |
| 0x04 | Calculated engine load       | A × 100/255      | %     |
| 0x11 | Absolute throttle position   | A × 100/255      | %     |
| 0x0F | Intake air temperature       | A − 40           | °C    |
| 0x1F | Run time since engine start  | A×256+B          | s     |
| 0x03 | Stored DTCs (Mode 03)        | —                | codes |

---

## Power management

- **Deep-sleep** is entered when the ignition sense pin stays LOW for
  `IGN_DEBOUNCE_MS` (3 s).  The MCU wakes every `DEEP_SLEEP_US` (60 s)
  to check if ignition is back on and drain any queued frames.
- **Load switch** (optional): connect the 3.3 V rail through a P-channel
  MOSFET controlled by the ignition sense line to fully cut power to
  peripherals during sleep.

---

## Telemetry MQTT topic

```
obdmonai/<client_id>/vehicle/<vin>/telemetry
```

Mosquitto `use_identity_as_username = true` — the device certificate CN
is used as the MQTT username and must match the device serial registered
in the backend.
