#pragma once
#include "cbor_payload.h"
#include <HardwareSerial.h>

// Attach the GNSS parser to a hardware serial port (UART2).
void gnss_begin(HardwareSerial &serial);

// Drain the GNSS UART and try to obtain a valid location fix.
// Returns true when a valid fix is decoded within timeout_ms.
// out is zeroed on failure.
bool gnss_read(GNSSReading &out, uint32_t timeout_ms = 2000);
