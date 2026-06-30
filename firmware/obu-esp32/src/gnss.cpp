#include "gnss.h"
#include <TinyGPSPlus.h>

static TinyGPSPlus     _gps;
static HardwareSerial *_serial = nullptr;

void gnss_begin(HardwareSerial &serial) {
    _serial = &serial;
}

bool gnss_read(GNSSReading &out, uint32_t timeout_ms) {
    out = {};
    if (!_serial) return false;

    uint32_t start = millis();
    while ((millis() - start) < timeout_ms) {
        while (_serial->available()) {
            _gps.encode((char)_serial->read());
        }
        if (_gps.location.isUpdated() && _gps.location.isValid()) {
            out.lat         = _gps.location.lat();
            out.lon         = _gps.location.lng();
            out.alt_m       = _gps.altitude.isValid()  ? (float)_gps.altitude.meters() : 0.0f;
            out.heading_deg = _gps.course.isValid()    ? (float)_gps.course.deg()       : 0.0f;
            out.speed_ms    = _gps.speed.isValid()     ? (float)(_gps.speed.kmph() / 3.6f) : 0.0f;
            out.valid       = true;
            return true;
        }
    }
    // No fix within timeout; return last-known position if available
    if (_gps.location.isValid()) {
        out.lat  = _gps.location.lat();
        out.lon  = _gps.location.lng();
        out.alt_m  = _gps.altitude.isValid() ? (float)_gps.altitude.meters() : 0.0f;
        out.valid  = false;  // stale — caller should note GNSS is unreliable
    }
    return false;
}
