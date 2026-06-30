#pragma once
#include <cstddef>
#include <cstdint>

// Initialise the SD-backed ring buffer. Call once in setup().
bool sf_begin();

// Append a CBOR-encoded frame to the ring buffer.
// Discards the oldest entry if the buffer is full.
bool sf_enqueue(const uint8_t *data, size_t len);

// Copy the oldest frame into data[]. Sets len on success.
bool sf_dequeue(uint8_t *data, size_t &len, size_t max_len);

// True when at least one frame is waiting.
bool sf_has_pending();

// Remove the oldest frame (call after a successful publish).
void sf_discard_oldest();
