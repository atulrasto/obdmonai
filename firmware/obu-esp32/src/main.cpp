#include <Arduino.h>
#include <WiFi.h>
#include <HardwareSerial.h>
#include <time.h>

#include "config.h"
#include "provision.h"
#include "obd.h"
#include "gnss.h"
#include "imu.h"
#include "cbor_payload.h"
#include "mqtt_uplink.h"
#include "store_forward.h"

// ── Globals ───────────────────────────────────────────────────────────────────

static ProvisionData  g_prov;
static HardwareSerial g_gnss_uart(2);   // UART2
static uint32_t       g_seq           = 0;
static uint32_t       g_last_poll_ms  = 0;
static uint32_t       g_ign_off_ms    = 0;
static uint8_t        g_cbor_buf[512];

// ── Helpers ───────────────────────────────────────────────────────────────────

static void wifi_connect() {
    WiFi.mode(WIFI_STA);
    WiFi.begin(g_prov.wifi_ssid.c_str(), g_prov.wifi_password.c_str());
    uint8_t tries = 20;
    while (WiFi.status() != WL_CONNECTED && tries--) delay(500);
    if (WiFi.status() == WL_CONNECTED) {
        // Sync clock via SNTP so device timestamps are accurate
        configTime(0, 0, "pool.ntp.org");
        Serial.printf("WiFi OK: %s\n", WiFi.localIP().toString().c_str());
    }
}

static void upload_pending() {
    if (!mqtt_connected() && !mqtt_reconnect()) return;
    while (sf_has_pending()) {
        size_t len = 0;
        if (!sf_dequeue(g_cbor_buf, len, sizeof g_cbor_buf)) {
            sf_discard_oldest();
            continue;
        }
        if (!mqtt_publish(g_cbor_buf, len)) break;  // broker busy — try again later
        sf_discard_oldest();
        mqtt_loop();
    }
}

static void take_reading() {
    OBDReading  obd  = {};
    GNSSReading gnss = {};
    IMUReading  imu  = {};

    obd_poll(obd);
    gnss_read(gnss);
    imu_read(imu);

    // DTC — up to 10 active codes
    char    dtc_raw[10][7] = {};
    uint8_t dtc_count      = 0;
    obd_read_dtc(dtc_raw, 10, dtc_count);

    const char *dtc_ptrs[10];
    for (uint8_t i = 0; i < dtc_count; i++) dtc_ptrs[i] = dtc_raw[i];

    TelemetryFrame frame = {
        .device_id = g_prov.device_id.c_str(),
        .ts        = (uint32_t)time(nullptr),  // device wall-clock (SNTP-synced)
        .seq       = ++g_seq,
        .gps       = gnss,
        .obd       = obd,
        .imu       = imu,
        .dtc       = dtc_ptrs,
        .dtc_count = dtc_count,
        .ign       = obd_ignition_on(),
    };

    size_t len = cbor_encode_frame(frame, g_cbor_buf, sizeof g_cbor_buf);
    if (len == 0) {
        Serial.println("CBOR encode overflow — reading dropped");
        return;
    }

    // Store first; drain queue after (application-layer at-least-once)
    sf_enqueue(g_cbor_buf, len);
    upload_pending();
}

// ── Arduino entry points ──────────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);
    Serial.println("\n[obdmonai] OBU booting");

    if (!provision_load(g_prov)) {
        Serial.println("[obdmonai] FATAL: provisioning failed — check NVS and /certs/ on LittleFS");
        while (true) delay(5000);
    }

    pinMode(PIN_IGN_SENSE, INPUT);

    if (!obd_init()) Serial.println("[obdmonai] WARN: TWAI init failed — OBD unavailable");

    g_gnss_uart.begin(GNSS_BAUD, SERIAL_8N1, PIN_GNSS_RX, PIN_GNSS_TX);
    gnss_begin(g_gnss_uart);

    if (!imu_begin()) Serial.println("[obdmonai] WARN: IMU not detected — continuing without IMU");

    sf_begin();  // SD ring buffer (best-effort; loses data if SD absent)

    wifi_connect();

    if (WiFi.status() == WL_CONNECTED) {
        MqttConfig mc = {
            .host        = g_prov.mqtt_host.c_str(),
            .port        = MQTT_PORT,
            .device_id   = g_prov.device_id.c_str(),
            .client_id   = g_prov.client_id.c_str(),
            .vin         = g_prov.vin.c_str(),
            .ca_cert     = g_prov.ca_cert.c_str(),
            .client_cert = g_prov.client_cert.c_str(),
            .client_key  = g_prov.client_key.c_str(),
        };
        mqtt_begin(mc);
        mqtt_reconnect();
    }

    Serial.println("[obdmonai] Setup complete");
}

void loop() {
    mqtt_loop();

    bool     ign = obd_ignition_on();
    uint32_t now = millis();

    if (!ign) {
        if (g_ign_off_ms == 0) g_ign_off_ms = now;

        if ((now - g_ign_off_ms) >= IGN_DEBOUNCE_MS) {
            // Ignition confirmed off: drain queue then enter deep-sleep.
            Serial.println("[obdmonai] Ignition off — draining queue then sleeping");
            upload_pending();
            esp_sleep_enable_timer_wakeup(DEEP_SLEEP_US);
            esp_deep_sleep_start();
            // No return after deep-sleep — MCU wakes via reset vector
        }
        return;
    }
    g_ign_off_ms = 0;  // reset debounce

    if ((now - g_last_poll_ms) >= POLL_INTERVAL_MS) {
        g_last_poll_ms = now;
        take_reading();
    }

    // Opportunistically drain the store-and-forward queue between readings
    if ((now % 2000u) < 50u) upload_pending();
}
