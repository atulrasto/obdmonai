"""PDF report endpoint — Tier A read-only; uses ReportLab.

GET /reports/vehicles/{vehicle_id}/pdf?from_ts=...&to_ts=...
Returns a binary PDF document.  No ML or LLM calls; pure deterministic data.
"""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.security.deps import get_tenant_db, require_role
from app.security.jwt import TokenData

router = APIRouter()

_UTC   = timezone.utc
_BLUE  = colors.HexColor("#3b82f6")
_LIGHT = colors.HexColor("#f8fafc")
_GRID  = colors.HexColor("#e2e8f0")


def _fmtsec(sec: float) -> str:
    h = int(sec) // 3600
    m = (int(sec) % 3600) // 60
    s = int(sec) % 60
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def _opt(val, fmt: str = ".1f", suffix: str = "") -> str:
    return f"{val:{fmt}}{suffix}" if val is not None else "—"


def _table(rows: list[list], col_widths: list, header_blue: bool = True) -> Table:
    t = Table(rows, colWidths=col_widths)
    style = [
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT]),
        ("GRID",           (0, 0), (-1, -1), 0.4, _GRID),
        ("TOPPADDING",     (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
        ("LEFTPADDING",    (0, 0), (-1, -1), 8),
        ("FONTSIZE",       (0, 1), (-1, -1), 9),
    ]
    if header_blue:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, 0), 9),
        ]
    t.setStyle(TableStyle(style))
    return t


def _build_pdf(
    make: str,
    model_name: str,
    year: int,
    vin: str,
    from_ts: datetime,
    to_ts: datetime,
    kpi: dict,
    obd: dict,
    trips: list[dict],
    generated_at: datetime,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        title=f"Vehicle Report — {make} {model_name}",
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    story  = []
    W      = 17 * cm  # usable page width

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(Paragraph("Vehicle Performance Report", styles["Title"]))
    story.append(Paragraph(f"{make} {model_name} ({year})", styles["Heading2"]))
    story.append(Paragraph(f"VIN: <font name='Courier'>{vin}</font>", styles["Normal"]))
    story.append(Paragraph(
        f"Period: {from_ts.strftime('%Y-%m-%d %H:%M UTC')} — {to_ts.strftime('%Y-%m-%d %H:%M UTC')}",
        styles["Normal"],
    ))
    story.append(Spacer(1, 0.5 * cm))

    # ── Driving KPIs ──────────────────────────────────────────────────────────
    story.append(Paragraph("Driving KPIs", styles["Heading3"]))
    story.append(Spacer(1, 0.2 * cm))

    kpi_rows = [
        ["Metric", "Value"],
        ["Readings collected",  str(kpi.get("reading_count", 0))],
        ["Distance",            _opt(kpi.get("distance_km"),    ".2f", " km")],
        ["Drive time",          _fmtsec(kpi.get("drive_time_sec") or 0)],
        ["Idle time",           _fmtsec(kpi.get("idle_time_sec")  or 0)],
        ["Average speed",       _opt(kpi.get("avg_speed"),      ".1f", " km/h")],
        ["Maximum speed",       _opt(kpi.get("max_speed"),      ".1f", " km/h")],
        ["Harsh braking events", str(kpi.get("harsh_braking_count") or 0)],
        ["Overspeed events",    str(kpi.get("overspeed_count")  or 0)],
    ]
    story.append(_table(kpi_rows, [10 * cm, 7 * cm]))
    story.append(Spacer(1, 0.75 * cm))

    # ── OBD Parameters ────────────────────────────────────────────────────────
    story.append(Paragraph("OBD / Engine Parameters (period averages)", styles["Heading3"]))
    story.append(Spacer(1, 0.2 * cm))

    fuel_start = obd.get("fuel_start")
    fuel_end   = obd.get("fuel_end")
    fuel_str   = (
        f"{fuel_start:.1f}% → {fuel_end:.1f}%"
        if fuel_start is not None and fuel_end is not None
        else "—"
    )

    obd_rows = [
        ["Parameter", "PID",   "Average",                                  "Min",                                   "Max"],
        ["Engine RPM",        "0x0C",
         _opt(obd.get("avg_rpm"),         ".0f", " rpm"),
         _opt(obd.get("min_rpm"),         ".0f", " rpm"),
         _opt(obd.get("max_rpm"),         ".0f", " rpm")],
        ["Vehicle Speed",     "0x0D",
         _opt(obd.get("avg_speed_obd"),   ".1f", " km/h"),
         _opt(obd.get("min_speed_obd"),   ".1f", " km/h"),
         _opt(obd.get("max_speed_obd"),   ".1f", " km/h")],
        ["Coolant Temp",      "0x05",
         _opt(obd.get("avg_coolant"),     ".1f", " °C"),
         _opt(obd.get("min_coolant"),     ".1f", " °C"),
         _opt(obd.get("max_coolant"),     ".1f", " °C")],
        ["Engine Load",       "0x04",
         _opt(obd.get("avg_load"),        ".1f", " %"),
         _opt(obd.get("min_load"),        ".1f", " %"),
         _opt(obd.get("max_load"),        ".1f", " %")],
        ["Throttle Position", "0x11",
         _opt(obd.get("avg_throttle"),    ".1f", " %"),
         _opt(obd.get("min_throttle"),    ".1f", " %"),
         _opt(obd.get("max_throttle"),    ".1f", " %")],
        ["Intake Air Temp",   "0x0F",
         _opt(obd.get("avg_intake"),      ".1f", " °C"),
         _opt(obd.get("min_intake"),      ".1f", " °C"),
         _opt(obd.get("max_intake"),      ".1f", " °C")],
        ["Fuel Level",        "0x2F",   fuel_str,   "—",   "—"],
        ["Engine Run Time",   "0x1F",
         _opt(obd.get("total_run_min"),   ".0f", " min"),
         "—", "—"],
    ]
    story.append(_table(obd_rows, [4.5 * cm, 1.8 * cm, 4 * cm, 3 * cm, 3 * cm]))
    story.append(Spacer(1, 0.75 * cm))

    # ── Trip table ────────────────────────────────────────────────────────────
    story.append(Paragraph("Trips (most recent 10)", styles["Heading3"]))
    story.append(Spacer(1, 0.2 * cm))

    if trips:
        trip_rows = [["#", "Started (UTC)", "Distance", "Duration", "Avg speed", "Max speed"]]
        for i, t in enumerate(trips[-10:], 1):
            raw_start = t.get("start_ts") or t.get("started_at")
            if raw_start:
                try:
                    started = datetime.fromisoformat(str(raw_start)).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    started = str(raw_start)[:16]
            else:
                started = "—"

            dur_sec  = t.get("duration_sec") or t.get("drive_time_sec") or 0
            a_spd    = t.get("avg_speed")
            mx_spd   = t.get("max_speed")
            trip_rows.append([
                str(i),
                started,
                _opt(t.get("distance_km"),  ".2f", " km"),
                _fmtsec(dur_sec),
                _opt(a_spd, ".0f", " km/h"),
                _opt(mx_spd, ".0f", " km/h"),
            ])
        story.append(_table(
            trip_rows,
            [1 * cm, 4.5 * cm, 2.8 * cm, 2.4 * cm, 2.8 * cm, 2.8 * cm],
        ))
    else:
        story.append(Paragraph("No trips recorded in this period.", styles["Normal"]))

    story.append(Spacer(1, cm))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(Paragraph(
        f"Generated by obdmonai at {generated_at.strftime('%Y-%m-%d %H:%M UTC')} · Confidential",
        styles["Normal"],
    ))

    doc.build(story)
    return buf.getvalue()


@router.get("/vehicles/{vehicle_id}/pdf", response_class=Response)
async def vehicle_report_pdf(
    vehicle_id: uuid.UUID,
    from_ts: datetime = Query(default=None),
    to_ts: datetime = Query(default=None),
    user: TokenData = Depends(require_role("owner", "fleet_admin", "viewer")),
    db: AsyncSession = Depends(get_tenant_db),
) -> Response:
    """Generate and return a PDF performance report for a vehicle."""
    now = datetime.now(_UTC)
    if to_ts is None:
        to_ts = now
    if from_ts is None:
        from_ts = to_ts - timedelta(hours=24)

    # Vehicle info
    vrow = (await db.execute(
        text("SELECT make, model_name, year, vin FROM vehicles WHERE id = :vid"),
        {"vid": str(vehicle_id)},
    )).fetchone()
    if vrow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")

    # KPIs via SECURITY DEFINER function
    krow = (await db.execute(
        text("SELECT * FROM analytics_vehicle_kpis(:vid, :cid, :from_ts, :to_ts)"),
        {"vid": str(vehicle_id), "cid": user.client_id, "from_ts": from_ts, "to_ts": to_ts},
    )).fetchone()
    kpi: dict = dict(krow._mapping) if krow else {}

    # OBD averages / min / max directly from telemetry (RLS active via get_tenant_db)
    orow = (await db.execute(
        text(
            "SELECT"
            "  AVG(obd_rpm)          AS avg_rpm,"
            "  MIN(obd_rpm)          AS min_rpm,"
            "  MAX(obd_rpm)          AS max_rpm,"
            "  AVG(obd_speed)        AS avg_speed_obd,"
            "  MIN(obd_speed)        AS min_speed_obd,"
            "  MAX(obd_speed)        AS max_speed_obd,"
            "  AVG(obd_coolant)      AS avg_coolant,"
            "  MIN(obd_coolant)      AS min_coolant,"
            "  MAX(obd_coolant)      AS max_coolant,"
            "  AVG(obd_load)         AS avg_load,"
            "  MIN(obd_load)         AS min_load,"
            "  MAX(obd_load)         AS max_load,"
            "  AVG(obd_throttle)     AS avg_throttle,"
            "  MIN(obd_throttle)     AS min_throttle,"
            "  MAX(obd_throttle)     AS max_throttle,"
            "  AVG(obd_intake_temp)  AS avg_intake,"
            "  MIN(obd_intake_temp)  AS min_intake,"
            "  MAX(obd_intake_temp)  AS max_intake,"
            "  first(obd_fuel_level, time) AS fuel_start,"
            "  last(obd_fuel_level,  time) AS fuel_end,"
            "  MAX(obd_run_time) / 60.0   AS total_run_min"
            " FROM telemetry"
            " WHERE vehicle_id = :vid AND client_id = :cid"
            "   AND time BETWEEN :from_ts AND :to_ts"
        ),
        {"vid": str(vehicle_id), "cid": str(user.client_id), "from_ts": from_ts, "to_ts": to_ts},
    )).fetchone()
    obd: dict = dict(orow._mapping) if orow else {}

    # Trips via SECURITY DEFINER function
    trip_rows = (await db.execute(
        text("SELECT * FROM analytics_list_trips(:vid, :cid, :from_ts, :to_ts)"),
        {"vid": str(vehicle_id), "cid": user.client_id, "from_ts": from_ts, "to_ts": to_ts},
    )).fetchall()
    trips = [dict(r._mapping) for r in trip_rows]

    pdf_bytes = _build_pdf(
        make=vrow.make,
        model_name=vrow.model_name,
        year=vrow.year,
        vin=vrow.vin,
        from_ts=from_ts,
        to_ts=to_ts,
        kpi=kpi,
        obd=obd,
        trips=trips,
        generated_at=now,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="vehicle_{vehicle_id}_report.pdf"',
        },
    )
