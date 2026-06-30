#pragma once
#include "cbor_payload.h"

// Initialise MPU-6050 over I2C (uses PIN_SDA / PIN_SCL from config.h).
bool imu_begin();

// Read accelerometer (m/s²) and gyroscope (rad/s) from MPU-6050.
bool imu_read(IMUReading &out);
