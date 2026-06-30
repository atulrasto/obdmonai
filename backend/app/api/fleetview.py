"""FleetView API — read-only NL summary endpoints.

GET /fleetview/vehicles/{vehicle_id}/summary

INVARIANT: no write operations; no tool use; identifiers redacted before LLM.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.fleetview.facts import assemble_facts
from app.fleetview.summarise import get_summary
from app.security.deps import get_tenant_db, require_role
from app.security.jwt import TokenData

router = APIRouter()


class SummaryResponse(BaseModel):
    vehicle_id: uuid.UUID
    summary: str
    computed_at: datetime


@router.get("/vehicles/{vehicle_id}/summary", response_model=SummaryResponse)
async def vehicle_summary(
    vehicle_id: uuid.UUID,
    hours: int = 24,
    user: TokenData = Depends(require_role("owner", "fleet_admin", "viewer")),
    db: AsyncSession = Depends(get_tenant_db),
) -> SummaryResponse:
    facts = await assemble_facts(vehicle_id, user.client_id, db, hours=hours)
    if facts is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found or not accessible",
        )
    summary = await get_summary(facts)
    return SummaryResponse(
        vehicle_id=vehicle_id,
        summary=summary,
        computed_at=datetime.now(timezone.utc),
    )
