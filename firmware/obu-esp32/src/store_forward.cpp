#include "store_forward.h"
#include "config.h"
#include <SD.h>
#include <SPI.h>
#include <stdio.h>

static uint32_t g_write_idx = 0;
static uint32_t g_read_idx  = 0;
static bool     g_ready     = false;

static void _path(char *buf, size_t sz, uint32_t idx) {
    snprintf(buf, sz, "/rbuf/%08lu.bin", (unsigned long)(idx % (uint32_t)RING_BUFFER_MAX));
}

static void _persist_indices() {
    File f = SD.open("/rbuf/idx", FILE_WRITE);
    if (!f) return;
    f.print(g_write_idx);
    f.print(',');
    f.print(g_read_idx);
    f.close();
}

bool sf_begin() {
    SPI.begin(PIN_SD_SCK, PIN_SD_MISO, PIN_SD_MOSI, PIN_SD_CS);
    if (!SD.begin(PIN_SD_CS)) return false;
    if (!SD.exists("/rbuf")) SD.mkdir("/rbuf");

    File f = SD.open("/rbuf/idx", FILE_READ);
    if (f) {
        g_write_idx = (uint32_t)f.parseInt();
        f.read();                              // consume comma
        g_read_idx  = (uint32_t)f.parseInt();
        f.close();
    }
    g_ready = true;
    return true;
}

bool sf_enqueue(const uint8_t *data, size_t len) {
    if (!g_ready) return false;
    // If ring is full, silently evict oldest to make room
    if ((g_write_idx - g_read_idx) >= (uint32_t)RING_BUFFER_MAX) {
        g_read_idx++;
        _persist_indices();
    }
    char path[32];
    _path(path, sizeof path, g_write_idx);
    File f = SD.open(path, FILE_WRITE);
    if (!f) return false;
    f.write(data, len);
    f.close();
    g_write_idx++;
    _persist_indices();
    return true;
}

bool sf_has_pending() {
    return g_ready && (g_read_idx < g_write_idx);
}

bool sf_dequeue(uint8_t *data, size_t &len, size_t max_len) {
    if (!sf_has_pending()) return false;
    char path[32];
    _path(path, sizeof path, g_read_idx);
    File f = SD.open(path, FILE_READ);
    if (!f) { g_read_idx++; _persist_indices(); return false; }
    size_t n = (size_t)f.size();
    if (n > max_len) { f.close(); return false; }
    f.read(data, n);
    f.close();
    len = n;
    return true;
}

void sf_discard_oldest() {
    if (!sf_has_pending()) return;
    char path[32];
    _path(path, sizeof path, g_read_idx);
    SD.remove(path);
    g_read_idx++;
    _persist_indices();
}
