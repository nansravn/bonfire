"""The safety-net timer tick (spec 6.3). Never reads the player count."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Callable

from bonfire.core.discord import render
from bonfire.core.events import Event
from bonfire.core.state import PreconditionFailed, StateRow, begin_extinguish
from bonfire.function.reconcile import needs_power_state, reconcile
from bonfire.function.worker import Clients

log = logging.getLogger("bonfire.watchdog")


def _player_count(row: StateRow) -> int | None:
    return None if row.last_player_count < 0 else row.last_player_count


def run_watchdog(c: Clients) -> None:
    now = c.clock.now()
    cfg = c.config
    stale = timedelta(minutes=cfg.heartbeat_stale_minutes)
    row = c.state.read()
    original = row.copy()
    after_write: list[Callable[[], None]] = []  # side effects that must follow the row write

    def post(message_id: str, **placeholders) -> None:
        try:
            c.webhook.post(render(message_id, **placeholders))
        except Exception as exc:
            log.warning("webhook post failed: %s", exc)

    def safety_extinguish(message_id: str, action: str, **placeholders) -> None:
        begin_extinguish(row, now)
        event = Event("watchdog", action, "function", now, session_id=row.session_id, player_count=_player_count(row))

        def act() -> None:
            c.compute.deallocate()
            post(message_id, **placeholders)
            c.events.record(event)

        after_write.append(act)

    power = None
    if needs_power_state(row, now):
        power = c.compute.power_state()
        result = reconcile(row, power, now, cfg)
        if result.deallocate:
            c.compute.deallocate()
        for event in result.events:
            c.events.record(event)
        row = result.row

    if row.vm_state == "lit" and row.session_started_at is not None:
        age = now - row.session_started_at
        if age >= timedelta(hours=cfg.max_session_hours):
            safety_extinguish("watchdog_ceiling", "ceiling", max_session_hours=cfg.max_session_hours)
        elif age >= timedelta(hours=cfg.max_session_hours - 1) and not row.ceiling_warned:
            row.ceiling_warned = True
            hours = int(age.total_seconds() // 3600)
            event = Event("watchdog", "ceiling_warning", "function", now, session_id=row.session_id,
                          player_count=_player_count(row), detail=f"lit {hours} h")
            after_write.append(lambda: (post("watchdog_ceiling_warning", h=hours, max_session_hours=cfg.max_session_hours),
                                        c.events.record(event)))
        if row.vm_state == "lit" and row.last_heartbeat is not None and now - row.last_heartbeat > stale:
            safety_extinguish("watchdog_heartbeat", "heartbeat_missing", heartbeat_stale_minutes=cfg.heartbeat_stale_minutes)
    elif row.vm_state == "igniting" and row.last_heartbeat is None and row.state_since is not None \
            and now - row.state_since >= stale:
        power = power if power is not None else c.compute.power_state()
        if power == "running":
            safety_extinguish("watchdog_boot_failed", "boot_failed", heartbeat_stale_minutes=cfg.heartbeat_stale_minutes)
    elif row.vm_state == "out" and row.last_heartbeat is not None and now - row.last_heartbeat > stale:
        power = power if power is not None else c.compute.power_state()
        if power == "running":  # drift: the row says out but something is running and silent
            event = Event("watchdog", "heartbeat_missing", "function", now, detail="drift: row out, vm running")
            after_write.append(lambda: (c.compute.deallocate(),
                                        post("watchdog_heartbeat", heartbeat_stale_minutes=cfg.heartbeat_stale_minutes),
                                        c.events.record(event)))

    if row != original:
        try:
            c.state.write(row)
        except PreconditionFailed:
            log.info("row changed during the tick; the next tick re-evaluates")
            return
    for act in after_write:
        act()
