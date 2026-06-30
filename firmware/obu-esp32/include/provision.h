#pragma once
#include <Arduino.h>

struct ProvisionData {
    String device_id;    // UUID string from NVS key "device_id"
    String client_id;    // tenant UUID
    String vin;          // vehicle VIN
    String wifi_ssid;
    String wifi_password;
    String mqtt_host;
    // TLS material loaded from LittleFS /certs/
    String ca_cert;      // PEM — broker CA
    String client_cert;  // PEM — device cert
    String client_key;   // PEM — device private key (never leave the unit)
};

// Load provisioning data from NVS namespace "obdmonai" and LittleFS certs.
// Returns false if any required field is missing.
bool provision_load(ProvisionData &out);
