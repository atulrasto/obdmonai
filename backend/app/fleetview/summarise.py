"""Build LLM prompt from VehicleFacts and call the Anthropic API.

No tool use — strictly text-in / text-out.
No DB writes.
Identifiers are kept out of the prompt by design; redact() is applied as
a safety net before the API call.

No tier_a imports.
"""
from __future__ import annotations

import anthropic

from app.config import settings
from app.fleetview.facts import VehicleFacts
from app.fleetview.redact import redact

_PLACEHOLDER = (
    "[FleetView summary unavailable — ANTHROPIC_API_KEY is not configured]"
)


def build_prompt(facts: VehicleFacts) -> str:
    """Build the user-turn prompt from structured, identifier-free facts."""
    lines = [
        "Summarize the following vehicle performance data for a fleet manager "
        "in 2–3 concise sentences. Focus on safety, efficiency, and any concerns. "
        "Do not invent information not present below.",
        "",
        f"Vehicle     : {facts.make} {facts.model_name} ({facts.year})",
        f"Period      : last {facts.period_hours} hours",
        f"Readings    : {facts.reading_count}",
        f"Distance    : {facts.distance_km:.2f} km",
    ]
    if facts.avg_speed_kmh is not None:
        lines.append(f"Avg speed   : {facts.avg_speed_kmh:.1f} km/h")
    if facts.max_speed_kmh is not None:
        lines.append(f"Max speed   : {facts.max_speed_kmh:.1f} km/h")
    if facts.driver_score is not None:
        lines.append(f"Driver score: {facts.driver_score:.0f} / 100")
    maint = (
        "anomaly detected" if facts.maintenance_anomaly
        else "no anomaly" if facts.maintenance_anomaly is not None
        else "N/A"
    )
    lines.append(f"Maintenance : {maint}")
    if facts.active_alert_count:
        lines.append(
            f"Alerts      : {facts.active_alert_count} active"
            f" ({', '.join(facts.alert_rules)})"
        )
    else:
        lines.append("Alerts      : none")
    lines.append(f"Trips       : {facts.trip_count}")
    return "\n".join(lines)


async def get_summary(facts: VehicleFacts) -> str:
    """Return a natural-language summary from the Anthropic API.

    Falls back to a placeholder when ANTHROPIC_API_KEY is not configured
    (e.g. in development / test environments).
    """
    if not settings.anthropic_api_key:
        return _PLACEHOLDER

    prompt = redact(build_prompt(facts))

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
        # No tools — FleetView is strictly read-only text generation
    )
    return message.content[0].text
