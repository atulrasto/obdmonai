#include "obd.h"
#include "config.h"
#include <Arduino.h>
#include <driver/twai.h>
#include <stdio.h>

// ── Internal helpers ──────────────────────────────────────────────────────────

static bool _send_pid(uint8_t mode, uint8_t pid) {
    twai_message_t req = {};
    req.identifier      = 0x7DFu;   // OBD-II functional broadcast address
    req.data_length_code = 8;
    req.data[0] = 0x02u;            // PCI: single frame, 2 data bytes follow
    req.data[1] = mode;
    req.data[2] = pid;
    for (int i = 3; i < 8; i++) req.data[i] = 0xAAu;  // ISO 15765-4 padding
    return twai_transmit(&req, pdMS_TO_TICKS(50)) == ESP_OK;
}

static bool _recv_response(uint8_t exp_mode, uint8_t exp_pid,
                            uint8_t *out, size_t &out_len,
                            uint32_t timeout_ms = 200) {
    twai_message_t resp;
    uint32_t deadline = timeout_ms;
    while (deadline--) {
        if (twai_receive(&resp, pdMS_TO_TICKS(1)) == ESP_OK) {
            if (resp.identifier >= 0x7E8u && resp.identifier <= 0x7EFu) {
                if (resp.data_length_code >= 3 &&
                    resp.data[1] == (exp_mode + 0x40u) &&
                    resp.data[2] == exp_pid) {
                    // Single-frame response: data[0] is PCI length byte
                    uint8_t n = (uint8_t)(resp.data[0] - 2u);
                    for (uint8_t i = 0; i < n && i < 4u; i++) out[i] = resp.data[3u + i];
                    out_len = n;
                    return true;
                }
            }
        }
    }
    return false;
}

// ── Public API ────────────────────────────────────────────────────────────────

bool obd_init() {
    twai_general_config_t gc = TWAI_GENERAL_CONFIG_DEFAULT(
        (gpio_num_t)PIN_CAN_TX, (gpio_num_t)PIN_CAN_RX, TWAI_MODE_NORMAL);
    twai_timing_config_t tc = TWAI_TIMING_CONFIG_500KBITS();
    twai_filter_config_t fc = TWAI_FILTER_CONFIG_ACCEPT_ALL();
    if (twai_driver_install(&gc, &tc, &fc) != ESP_OK) return false;
    return twai_start() == ESP_OK;
}

bool obd_poll(OBDReading &out) {
    out = {};
    uint8_t d[4]; size_t n;

    // 0x0C — Engine RPM: (A*256+B)/4 RPM
    if (_send_pid(0x01, 0x0C) && _recv_response(0x01, 0x0C, d, n) && n >= 2)
        out.rpm = ((d[0] << 8u) | d[1]) / 4.0f;

    // 0x0D — Vehicle speed km/h: A
    if (_send_pid(0x01, 0x0D) && _recv_response(0x01, 0x0D, d, n) && n >= 1)
        out.speed_kmh = d[0];

    // 0x05 — Engine coolant temperature: A − 40 °C
    if (_send_pid(0x01, 0x05) && _recv_response(0x01, 0x05, d, n) && n >= 1)
        out.coolant_c = d[0] - 40.0f;

    // 0x2F — Fuel tank level: A × 100/255 %
    if (_send_pid(0x01, 0x2F) && _recv_response(0x01, 0x2F, d, n) && n >= 1)
        out.fuel_pct = d[0] * 100.0f / 255.0f;

    // 0x04 — Calculated engine load: A × 100/255 %
    if (_send_pid(0x01, 0x04) && _recv_response(0x01, 0x04, d, n) && n >= 1)
        out.load_pct = d[0] * 100.0f / 255.0f;

    // 0x11 — Absolute throttle position: A × 100/255 %
    if (_send_pid(0x01, 0x11) && _recv_response(0x01, 0x11, d, n) && n >= 1)
        out.throttle_pct = d[0] * 100.0f / 255.0f;

    // 0x0F — Intake air temperature: A − 40 °C
    if (_send_pid(0x01, 0x0F) && _recv_response(0x01, 0x0F, d, n) && n >= 1)
        out.intake_temp_c = d[0] - 40.0f;

    // 0x1F — Run time since engine start: (A*256+B) s
    if (_send_pid(0x01, 0x1F) && _recv_response(0x01, 0x1F, d, n) && n >= 2)
        out.run_time_s = ((uint32_t)d[0] << 8u) | d[1];

    out.valid = true;
    return true;
}

bool obd_read_dtc(char dtc_buf[][7], uint8_t max_dtc, uint8_t &dtc_count) {
    dtc_count = 0;

    twai_message_t req = {};
    req.identifier       = 0x7DFu;
    req.data_length_code = 8;
    req.data[0] = 0x01u;  // PCI: single frame, 1 data byte
    req.data[1] = 0x03u;  // Mode 03 — request stored DTCs
    for (int i = 2; i < 8; i++) req.data[i] = 0xAAu;

    if (twai_transmit(&req, pdMS_TO_TICKS(50)) != ESP_OK) return false;

    twai_message_t resp;
    if (twai_receive(&resp, pdMS_TO_TICKS(200)) != ESP_OK) return false;
    if (resp.data[1] != 0x43u) return false;  // 0x40 + mode 0x03

    uint8_t n = resp.data[0] & 0x0Fu;  // number of DTCs in this frame
    static const char pfx[] = {'P','C','B','U'};

    for (uint8_t i = 0; i < n && dtc_count < max_dtc; i++) {
        uint8_t a = resp.data[2u + i * 2u];
        uint8_t b = resp.data[3u + i * 2u];
        if (a == 0 && b == 0) continue;
        // Format: Pxxxx / Cxxxx / Bxxxx / Uxxxx
        snprintf(dtc_buf[dtc_count++], 7, "%c%01X%02X%02X",
                 pfx[(a >> 6u) & 0x03u],
                 (a >> 4u) & 0x03u,
                 a & 0x0Fu,
                 b);
    }
    return true;
}

bool obd_ignition_on() {
    return digitalRead(PIN_IGN_SENSE) == HIGH;
}
