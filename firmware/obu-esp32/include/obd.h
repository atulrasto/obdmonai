#pragma once
#include "cbor_payload.h"

// Initialise the TWAI (CAN) controller.
// Must be called once in setup().
bool obd_init();

// Poll all OBD-II PIDs and populate `out`.
// Returns true even if some PIDs time out (partial data still useful).
bool obd_poll(OBDReading &out);

// Read stored DTC codes via Mode 0x03.
// dtc_buf: caller-allocated array of char[7] (e.g. "P0300\0").
// Returns true on success; dtc_count may be 0 (no faults).
bool obd_read_dtc(char dtc_buf[][7], uint8_t max_dtc, uint8_t &dtc_count);

// Debounced ignition sense: reads PIN_IGN_SENSE.
bool obd_ignition_on();
