"""In-process registry of active simulation tasks.

Tasks are asyncio.Task objects stored in a module-level dict keyed by vehicle_id.
The FastAPI process is single-process so this is safe without extra locking.
"""
from __future__ import annotations

import asyncio
import logging

from app.simulator.engine import SimConfig, simulate_vehicle

log = logging.getLogger(__name__)

_tasks: dict[str, asyncio.Task] = {}


def is_running(vehicle_id: str) -> bool:
    task = _tasks.get(vehicle_id)
    return task is not None and not task.done()


def start(vehicle_id: str, cfg: SimConfig) -> None:
    if is_running(vehicle_id):
        return
    task = asyncio.create_task(
        simulate_vehicle(cfg),
        name=f"sim-{vehicle_id[:8]}",
    )
    _tasks[vehicle_id] = task
    log.info("Simulator started  vehicle=%s device=%s", vehicle_id, cfg["device_id"])


def stop(vehicle_id: str) -> None:
    task = _tasks.pop(vehicle_id, None)
    if task and not task.done():
        task.cancel()
        log.info("Simulator stopped  vehicle=%s", vehicle_id)


def stop_all() -> None:
    for vehicle_id in list(_tasks):
        stop(vehicle_id)


def running_ids() -> list[str]:
    return [vid for vid, t in _tasks.items() if not t.done()]
