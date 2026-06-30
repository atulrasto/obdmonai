#pragma once
#include <cstddef>
#include <cstdint>

// ── Telemetry reading structures ──────────────────────────────────────────────

struct OBDReading {
    float    speed_kmh;
    float    rpm;
    float    coolant_c;
    float    fuel_pct;
    float    load_pct;
    float    throttle_pct;
    float    intake_temp_c;
    uint32_t run_time_s;
    bool     valid;
};

struct GNSSReading {
    double lat, lon;
    float  alt_m;
    float  heading_deg;
    float  speed_ms;   // m/s
    bool   valid;
};

struct IMUReading {
    float ax, ay, az;   // m/s²
    float gx, gy, gz;   // rad/s
};

struct TelemetryFrame {
    const char  *device_id;
    uint32_t     ts;           // Unix epoch seconds (device clock)
    uint32_t     seq;
    GNSSReading  gps;
    OBDReading   obd;
    IMUReading   imu;
    const char **dtc;
    uint8_t      dtc_count;
    bool         ign;
};

// ── Encode frame → CBOR map ───────────────────────────────────────────────────
// Returns number of bytes written, or 0 on overflow.
size_t cbor_encode_frame(const TelemetryFrame &frame, uint8_t *out, size_t out_size);
