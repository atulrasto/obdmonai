#include "provision.h"
#include <Preferences.h>
#include <LittleFS.h>

static String _read_file(const char *path) {
    File f = LittleFS.open(path, "r");
    if (!f) return {};
    String s = f.readString();
    f.close();
    return s;
}

bool provision_load(ProvisionData &out) {
    // ── 1. NVS ────────────────────────────────────────────────────────────────
    Preferences prefs;
    prefs.begin("obdmonai", /*readOnly=*/true);

    out.device_id     = prefs.getString("device_id",  "");
    out.client_id     = prefs.getString("client_id",  "");
    out.vin           = prefs.getString("vin",         "");
    out.wifi_ssid     = prefs.getString("wifi_ssid",  "");
    out.wifi_password = prefs.getString("wifi_pass",  "");
    out.mqtt_host     = prefs.getString("mqtt_host",  "");

    prefs.end();

    if (out.device_id.isEmpty() || out.client_id.isEmpty() ||
        out.vin.isEmpty()       || out.mqtt_host.isEmpty()) {
        return false;
    }

    // ── 2. TLS certs from LittleFS ────────────────────────────────────────────
    if (!LittleFS.begin(/*formatOnFail=*/false)) return false;

    out.ca_cert     = _read_file("/certs/ca.pem");
    out.client_cert = _read_file("/certs/device.crt");
    out.client_key  = _read_file("/certs/device.key");

    return !out.ca_cert.isEmpty() &&
           !out.client_cert.isEmpty() &&
           !out.client_key.isEmpty();
}
