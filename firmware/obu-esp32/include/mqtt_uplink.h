#pragma once
#include <cstddef>
#include <cstdint>

struct MqttConfig {
    const char *host;
    uint16_t    port;
    const char *device_id;   // used as MQTT client-id (= cert CN)
    const char *client_id;   // tenant UUID (part of topic)
    const char *vin;
    const char *ca_cert;     // PEM
    const char *client_cert; // PEM
    const char *client_key;  // PEM
};

// Initialise TLS context and set broker target.
bool mqtt_begin(const MqttConfig &cfg);

bool mqtt_connected();

// Attempt one reconnect; returns true when the connection succeeds.
bool mqtt_reconnect();

// Publish one CBOR frame (QoS 0 at the MQTT layer; durability is provided
// by the store-and-forward ring buffer — frames are only discarded after
// a successful publish, giving application-layer at-least-once semantics).
bool mqtt_publish(const uint8_t *data, size_t len);

// Must be called frequently to service the PubSubClient loop.
void mqtt_loop();
