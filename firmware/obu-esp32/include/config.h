#pragma once
#include <cstdint>

// ── CAN / OBD-II (TWAI) ──────────────────────────────────────────────────────
// SN65HVD230 transceiver wiring:
//   GPIO5 → SN65HVD230 TXD → OBD-II pin 6  (CAN-H)
//   GPIO4 ← SN65HVD230 RXD ← OBD-II pin 14 (CAN-L)
constexpr int PIN_CAN_TX = 5;
constexpr int PIN_CAN_RX = 4;

// ── GNSS — UART2 (NEO-6M or compatible) ──────────────────────────────────────
constexpr int     PIN_GNSS_TX  = 17;
constexpr int     PIN_GNSS_RX  = 16;
constexpr uint32_t GNSS_BAUD   = 9600;

// ── IMU — MPU-6050 over I2C ───────────────────────────────────────────────────
constexpr int PIN_SDA = 21;
constexpr int PIN_SCL = 22;

// ── SD card — SPI (ring buffer / store-and-forward) ──────────────────────────
constexpr int PIN_SD_CS   = 15;
constexpr int PIN_SD_MOSI = 23;
constexpr int PIN_SD_MISO = 19;
constexpr int PIN_SD_SCK  = 18;

// ── Ignition sense ────────────────────────────────────────────────────────────
// Active-high: HIGH = ignition on.
// Use a voltage divider so 12 V ignition line → 3.3 V GPIO.
// GPIO34 is input-only (no internal pull-up).
constexpr int PIN_IGN_SENSE = 34;

// ── Timing ────────────────────────────────────────────────────────────────────
constexpr uint32_t POLL_INTERVAL_MS   = 10000;   // 10 s between readings
constexpr uint32_t MQTT_RECONNECT_MS  = 5000;    // MQTT reconnect retry interval
constexpr uint32_t IGN_DEBOUNCE_MS    = 3000;    // ignition-off must persist 3 s
constexpr uint64_t DEEP_SLEEP_US      = 60ULL * 1000000ULL;  // 60 s deep-sleep

// ── MQTT / network ────────────────────────────────────────────────────────────
constexpr uint16_t MQTT_PORT          = 8883;    // MQTT over TLS
constexpr int      RING_BUFFER_MAX    = 500;     // max queued frames on SD
