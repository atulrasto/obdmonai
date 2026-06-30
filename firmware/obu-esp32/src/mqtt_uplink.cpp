#include "mqtt_uplink.h"
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>

static WiFiClientSecure g_tls;
static PubSubClient     g_mqtt(g_tls);

// Copies of config strings — valid for lifetime of program (ProvisionData is global)
static MqttConfig g_cfg;
static char       g_topic[160];

bool mqtt_begin(const MqttConfig &cfg) {
    g_cfg = cfg;

    // Topic: obdmonai/<client_id>/vehicle/<vin>/telemetry
    snprintf(g_topic, sizeof g_topic, "obdmonai/%s/vehicle/%s/telemetry",
             cfg.client_id, cfg.vin);

    g_tls.setCACert(cfg.ca_cert);
    g_tls.setCertificate(cfg.client_cert);
    g_tls.setPrivateKey(cfg.client_key);

    g_mqtt.setServer(cfg.host, cfg.port);
    g_mqtt.setBufferSize(2048);
    g_mqtt.setKeepAlive(60);
    g_mqtt.setSocketTimeout(10);
    return true;
}

bool mqtt_connected() { return g_mqtt.connected(); }

bool mqtt_reconnect() {
    if (g_mqtt.connected()) return true;
    // Mosquitto use_identity_as_username=true — device cert CN becomes username
    return g_mqtt.connect(g_cfg.device_id);
}

bool mqtt_publish(const uint8_t *data, size_t len) {
    return g_mqtt.publish(g_topic, data, (unsigned int)len, /*retain=*/false);
}

void mqtt_loop() { g_mqtt.loop(); }
