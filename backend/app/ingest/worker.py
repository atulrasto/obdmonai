"""MQTT ingest worker — subscribes to telemetry topics and writes to the hypertable.

Run as: python -m app.ingest.worker
"""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
from datetime import timezone

import cbor2
from aiomqtt import Client, MqttError
from sqlalchemy import String, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.ingest.schemas import TelemetryPayload
from app.tier_a.engine import run_for_device
from app.tier_a.rules import TelemetryReading

log = logging.getLogger(__name__)

TOPIC_FILTER = "obdmonai/+/vehicle/+/telemetry"

# Bind p_dtc with explicit ARRAY(String) so asyncpg serialises Python list → text[].
_INGEST_SQL = text("""
    SELECT ingest_record_telemetry(
        :p_time,        :p_client_id,   :p_vehicle_id,  :p_device_id,   :p_seq,
        :p_gps_lat,     :p_gps_lon,     :p_gps_alt,     :p_gps_hdg,     :p_gps_spd,
        :p_obd_rpm,     :p_obd_speed,   :p_obd_coolant, :p_obd_load,    :p_obd_throttle,
        :p_obd_intake_temp, :p_obd_fuel_level, :p_obd_run_time,
        :p_imu_ax,      :p_imu_ay,      :p_imu_az,
        :p_imu_gx,      :p_imu_gy,      :p_imu_gz,
        :p_dtc,         :p_ign
    )
""").bindparams(bindparam("p_dtc", type_=ARRAY(String)))


def _decode(raw: bytes) -> dict:
    """Try CBOR first, fall back to JSON."""
    try:
        return cbor2.loads(raw)
    except Exception:
        return json.loads(raw)


async def process_message(
    topic: str,
    raw: bytes,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Validate and persist one telemetry message.

    Silently drops the message (with a log warning) if:
    - topic structure is unexpected
    - payload is not valid CBOR/JSON
    - payload fails schema validation
    - device is unknown or inactive
    - topic client_id / vin don't match the device's registration (spoofed tenant)
    Duplicate (device_id, seq) pairs are silently ignored.
    """
    parts = topic.split("/")
    if len(parts) != 5 or parts[0] != "obdmonai" or parts[2] != "vehicle" or parts[4] != "telemetry":
        log.warning("Unexpected topic structure: %s", topic)
        return

    topic_client_id = parts[1]
    topic_vin = parts[3]

    try:
        data = _decode(raw)
    except Exception as exc:
        log.warning("Malformed payload on %s: %s", topic, exc)
        return

    try:
        payload = TelemetryPayload.model_validate(data)
    except Exception as exc:
        log.warning("Schema validation failed on %s: %s", topic, exc)
        return

    rules_reading: TelemetryReading | None = None

    async with session_factory() as session:
        async with session.begin():
            row = (await session.execute(
                text("SELECT * FROM ingest_get_device(:did)"),
                {"did": str(payload.device_id)},
            )).fetchone()

            if row is None:
                log.warning("Unknown device %s on topic %s", payload.device_id, topic)
                return

            if not row.is_active:
                log.warning("Inactive device %s", payload.device_id)
                return

            if str(row.client_id) != topic_client_id:
                log.warning(
                    "Spoofed-tenant: device %s belongs to client %s but topic claims %s",
                    payload.device_id, row.client_id, topic_client_id,
                )
                return

            if row.vin != topic_vin:
                log.warning(
                    "VIN mismatch: device %s registered vin=%s but topic vin=%s",
                    payload.device_id, row.vin, topic_vin,
                )
                return

            ts = payload.ts
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)

            inserted: bool = (await session.execute(
                _INGEST_SQL,
                {
                    "p_time": ts,
                    "p_client_id": str(row.client_id),
                    "p_vehicle_id": str(row.vehicle_id),
                    "p_device_id": str(payload.device_id),
                    "p_seq": payload.seq,
                    "p_gps_lat": payload.gps.lat,
                    "p_gps_lon": payload.gps.lon,
                    "p_gps_alt": payload.gps.alt,
                    "p_gps_hdg": payload.gps.hdg,
                    "p_gps_spd": payload.gps.spd,
                    "p_obd_rpm": payload.obd.rpm,
                    "p_obd_speed": payload.obd.speed,
                    "p_obd_coolant": payload.obd.coolant,
                    "p_obd_load": payload.obd.load,
                    "p_obd_throttle": payload.obd.throttle,
                    "p_obd_intake_temp": payload.obd.intake_temp,
                    "p_obd_fuel_level": payload.obd.fuel_level,
                    "p_obd_run_time": payload.obd.run_time,
                    "p_imu_ax": payload.imu.ax,
                    "p_imu_ay": payload.imu.ay,
                    "p_imu_az": payload.imu.az,
                    "p_imu_gx": payload.imu.gx,
                    "p_imu_gy": payload.imu.gy,
                    "p_imu_gz": payload.imu.gz,
                    "p_dtc": payload.dtc,
                    "p_ign": payload.ign,
                },
            )).scalar()

            if inserted:
                log.info("Inserted seq=%s device=%s", payload.seq, payload.device_id)
                rules_reading = TelemetryReading(
                    device_id=str(payload.device_id),
                    vehicle_id=str(row.vehicle_id),
                    client_id=str(row.client_id),
                    ts=ts,
                    seq=payload.seq,
                    obd_speed=payload.obd.speed,
                    obd_coolant=payload.obd.coolant,
                    obd_rpm=payload.obd.rpm,
                    obd_fuel_level=payload.obd.fuel_level,
                    imu_ax=payload.imu.ax,
                    gps_lat=payload.gps.lat,
                    gps_lon=payload.gps.lon,
                    dtc=list(payload.dtc),
                    ign=payload.ign,
                )
            else:
                log.info("Duplicate seq=%s device=%s — skipped", payload.seq, payload.device_id)

    # Ingest transaction committed; evaluate rules in a separate transaction.
    if rules_reading is not None:
        try:
            await run_for_device(rules_reading, session_factory)
        except Exception as exc:
            log.error("Rule evaluation failed for device=%s: %s", rules_reading.device_id, exc)


def _make_tls_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.load_verify_locations(settings.mqtt_ca_cert)
    ctx.load_cert_chain(settings.mqtt_client_cert, settings.mqtt_client_key)
    return ctx


def _make_session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
        connect_args={"prepared_statement_cache_size": 0},
    )
    return async_sessionmaker(engine, expire_on_commit=False)


async def main() -> None:
    logging.basicConfig(level=settings.log_level)
    sf = _make_session_factory()
    tls_ctx = _make_tls_context()
    reconnect_interval = 5

    while True:
        try:
            async with Client(
                settings.mqtt_host,
                port=settings.mqtt_port,
                tls_context=tls_ctx,
            ) as client:
                log.info("Connected to MQTT broker %s:%s", settings.mqtt_host, settings.mqtt_port)
                await client.subscribe(TOPIC_FILTER)
                async for msg in client.messages:
                    await process_message(str(msg.topic), msg.payload, sf)
        except MqttError as exc:
            log.warning("MQTT disconnected (%s) — reconnecting in %ss", exc, reconnect_interval)
            await asyncio.sleep(reconnect_interval)


if __name__ == "__main__":
    asyncio.run(main())
