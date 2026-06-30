#include "imu.h"
#include "config.h"
#include <Wire.h>
#include <MPU6050.h>

static MPU6050 _mpu;

bool imu_begin() {
    Wire.begin(PIN_SDA, PIN_SCL);
    _mpu.initialize();
    return _mpu.testConnection();
}

bool imu_read(IMUReading &out) {
    int16_t ax, ay, az, gx, gy, gz;
    _mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);

    // MPU-6050 factory defaults:  ±2 g range → 16384 LSB/g;  ±250 °/s → 131 LSB/(°/s)
    constexpr float ACCEL_SCALE = 9.80665f / 16384.0f;           // → m/s²
    constexpr float GYRO_SCALE  = (3.14159265f / 180.0f) / 131.0f; // → rad/s

    out.ax = ax * ACCEL_SCALE;
    out.ay = ay * ACCEL_SCALE;
    out.az = az * ACCEL_SCALE;
    out.gx = gx * GYRO_SCALE;
    out.gy = gy * GYRO_SCALE;
    out.gz = gz * GYRO_SCALE;
    return true;
}
