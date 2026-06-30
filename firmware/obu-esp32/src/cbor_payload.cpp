#include "cbor_payload.h"
#include <cstring>

// ── Minimal CBOR writer ───────────────────────────────────────────────────────
// Supports: uint, text-string, float32, bool, array, map (definite length).
// Enough to encode our fixed-schema TelemetryFrame.

struct CborBuf {
    uint8_t *data;
    size_t   capacity;
    size_t   len = 0;

    void put(uint8_t b)                          { if (len < capacity) data[len++] = b; }
    void put_bytes(const uint8_t *b, size_t n)  { for (size_t i = 0; i < n; i++) put(b[i]); }

    void type_len(uint8_t major, uint64_t v) {
        uint8_t mt = (major & 0x07u) << 5u;
        if      (v <= 23u)           { put(mt | (uint8_t)v); }
        else if (v <= 0xFFu)         { put(mt | 24u); put((uint8_t)v); }
        else if (v <= 0xFFFFu)       { put(mt | 25u); put((uint8_t)(v>>8)); put((uint8_t)v); }
        else if (v <= 0xFFFFFFFFu)   { put(mt | 26u); put((uint8_t)(v>>24)); put((uint8_t)(v>>16)); put((uint8_t)(v>>8)); put((uint8_t)v); }
        else {
            put(mt | 27u);
            for (int i = 7; i >= 0; i--) put((uint8_t)((v >> (i*8)) & 0xFFu));
        }
    }

    void uint_(uint64_t v) { type_len(0, v); }

    void text(const char *s, size_t n = 0) {
        if (n == 0) n = strlen(s);
        type_len(3, n);
        put_bytes(reinterpret_cast<const uint8_t*>(s), n);
    }

    void float32(float v) {
        put(0xFAu);
        uint32_t bits = 0;
        memcpy(&bits, &v, sizeof bits);
        put((uint8_t)(bits >> 24u));
        put((uint8_t)(bits >> 16u));
        put((uint8_t)(bits >>  8u));
        put((uint8_t)(bits));
    }

    void bool_(bool v) { put(v ? 0xF5u : 0xF4u); }

    void array_open(size_t n) { type_len(4, n); }
    void map_open(size_t n)   { type_len(5, n); }
};

size_t cbor_encode_frame(const TelemetryFrame &f, uint8_t *out, size_t out_size) {
    CborBuf b{out, out_size};

    b.map_open(8);

    // device_id
    b.text("device_id");      b.text(f.device_id);

    // ts (Unix epoch integer — backend field_validator converts to datetime)
    b.text("ts");             b.uint_(f.ts);

    // seq
    b.text("seq");            b.uint_(f.seq);

    // gps
    b.text("gps"); b.map_open(5);
    b.text("lat"); b.float32((float)f.gps.lat);
    b.text("lon"); b.float32((float)f.gps.lon);
    b.text("alt"); b.float32(f.gps.alt_m);
    b.text("hdg"); b.float32(f.gps.heading_deg);
    b.text("spd"); b.float32(f.gps.speed_ms);

    // obd
    b.text("obd"); b.map_open(8);
    b.text("speed");       b.float32(f.obd.speed_kmh);
    b.text("rpm");         b.float32(f.obd.rpm);
    b.text("coolant");     b.float32(f.obd.coolant_c);
    b.text("fuel_level");  b.float32(f.obd.fuel_pct);
    b.text("load");        b.float32(f.obd.load_pct);
    b.text("throttle");    b.float32(f.obd.throttle_pct);
    b.text("intake_temp"); b.float32(f.obd.intake_temp_c);
    b.text("run_time");    b.uint_(f.obd.run_time_s);

    // imu
    b.text("imu"); b.map_open(6);
    b.text("ax"); b.float32(f.imu.ax);
    b.text("ay"); b.float32(f.imu.ay);
    b.text("az"); b.float32(f.imu.az);
    b.text("gx"); b.float32(f.imu.gx);
    b.text("gy"); b.float32(f.imu.gy);
    b.text("gz"); b.float32(f.imu.gz);

    // dtc
    b.text("dtc"); b.array_open(f.dtc_count);
    for (uint8_t i = 0; i < f.dtc_count; i++) b.text(f.dtc[i]);

    // ign
    b.text("ign"); b.bool_(f.ign);

    return (b.len > out_size) ? 0 : b.len;
}
