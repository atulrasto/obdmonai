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

_UTC = timezone.utc
_BLUE = colors.HexColor("#3b82f6")
_LIGHT = colors.HexColor("#f8fafc")
_GRID = colors.HexColor("#e2e8f0")


def _fmtsec(sec: float) -> str:
    h = int(sec) // 3600
    m = (int(sec) % 3600) // 60
    return f"{h}h {m}m" if h else f"{m}m"


def _build_pdf(
    make: str,
    model_name: str,
    year: int,
    vin: str,
    from_ts: datetime,
    to_ts: datetime,
    kpi: dict,
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
    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(Paragraph("Vehicle Performance Report", styles["Title"]))
    story.append(Paragraph(f"{make} {model_name} ({year})", styles["Heading2"]))
    story.append(Paragraph(f"VIN: <font name='Courier'>{vin}</font>", styles["Normal"]))
    story.append(Paragraph(
        f"Period: {from_ts.strftime('%Y-%m-%d %H:%M UTC')} — {to_ts.strftime('%Y-%m-%d %H:%M UTC')}",
        styles["Normal"],
    ))
    story.append(Spacer(1, 0.5 * cm))

    # ── KPI table ─────────────────────────────────────────────────────────────
    story.append(Paragraph("Driving KPIs", styles["Heading3"]))
    story.append(Spacer(1, 0.2 * cm))

    avg_spd = kpi.get("avg_speed")
    max_spd = kpi.get("max_speed")

    kpi_rows = [
        ["Metric", "Value"],
        ["Readings collected", str(kpi.get("reading_count", 0))],
        ["Distance", f"{kpi.get('distance_km', 0):.2f} km"],
        ["Drive time", _fmtsec(kpi.get("drive_time_sec", 0))],
        ["Idle time", _fmtsec(kpi.get("idle_time_sec", 0))],
        ["Average speed", f"{avg_spd:.1f} km/h" if avg_spd is not None else "—"],
        ["Maximum speed", f"{max_spd:.1f} km/h" if max_spd is not None else "—"],
        ["Harsh events", str(kpi.get("harsh_events", 0))],
    ]

    kpi_table = Table(kpi_rows, colWidths=[9 * cm, 7 * cm])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), _BLUE),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT]),
        ("GRID",          (0, 0), (-1, -1), 0.4, _GRID),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 0.75 * cm))

    # ── Trip table ────────────────────────────────────────────────────────────
    story.append(Paragraph("Trips (most recent 10)", styles["Heading3"]))
    story.append(Spacer(1, 0.2 * cm))

    if trips:
        trip_rows = [["#", "Started", "Distance", "Drive time", "Avg speed"]]
        for i, t in enumerate(trips[-10:], 1):
            started = datetime.fromisoformat(str(t.get("started_at", ""))).strftime("%Y-%m-%d %H:%M") if t.get("started_at") else "—"
            a_spd = t.get("avg_speed")
            trip_rows.append([
                str(i),
                started,
                f"{t.get('distance_km', 0):.2f} km",
                _fmtsec(t.get("drive_time_sec", 0)),
                f"{a_spd:.0f} km/h" if a_spd is not None else "—",
            ])
        trip_table = Table(trip_rows, colWidths=[1.5 * cm, 5 * cm, 3.5 * cm, 3 * cm, 3.5 * cm])
        trip_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), _BLUE),
            ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT]),
            ("GRID",          (0, 0), (-1, -1), 0.4, _GRID),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("FONTSIZE",      (0, 1), (-1, -1), 9),
        ]))
        story.append(trip_table)
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

    # Vehicle info (RLS ensures tenant isolation)
    vrow = (await db.execute(
        text("SELECT make, model_name, year, vin FROM vehicles WHERE id = :vid"),
        {"vid": str(vehicle_id)},
    )).fetchone()
    if vrow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")

    # KPIs via SECURITY DEFINER function
    krow = (await db.execute(
        text("SELECT * FROM analytics_vehicle_kpis(:vid, :cid, :from_ts, :to_ts)"),
        {
            "vid": str(vehicle_id),
            "cid": user.client_id,
            "from_ts": from_ts,
            "to_ts": to_ts,
        },
    )).fetchone()
    kpi: dict = dict(krow._mapping) if krow else {}

    # Trips via SECURITY DEFINER function
    trip_rows = (await db.execute(
        text("SELECT * FROM analytics_list_trips(:vid, :cid, :from_ts, :to_ts)"),
        {
            "vid": str(vehicle_id),
            "cid": user.client_id,
            "from_ts": from_ts,
            "to_ts": to_ts,
        },
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
