"""The agent's per-tick decision (spec section 7). One process per systemd timer tick."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from bonfire.agent.adapter import TIMEOUTS, Adapter
from bonfire.agent.backup import BackupStore, clear_staging
from bonfire.core.clock import Clock
from bonfire.core.compute import Compute
from bonfire.core.config import UNKNOWN_ALERT_MINUTES, Config
from bonfire.core.discord import Webhook, render
from bonfire.core.events import Event, EventSink
from bonfire.core.state import PreconditionFailed, StateRow, StateTable, begin_extinguish, begin_ignite

log = logging.getLogger("bonfire.agent")
MAX_ATTEMPTS = 3
HEALTH_VALUES = {"ok", "degraded", "crashed"}


@dataclass
class AgentClients:
    config: Config
    clock: Clock
    state: StateTable
    events: EventSink
    compute: Compute
    webhook: Webhook
    adapter: Adapter
    backup: BackupStore
    staging_dir: Path
    ready_timeout_minutes: int
    stop_grace_seconds: int
    ready_poll_seconds: float = 10.0
    ready_poll_budget_seconds: float = 50.0


def run_check(c: AgentClients) -> int:
    for _ in range(MAX_ATTEMPTS):
        try:
            _tick(c)
            return 0
        except PreconditionFailed:
            log.info("state row changed under us; re-reading")
    log.warning("gave up after %d conflicting writes; the next tick retries", MAX_ATTEMPTS)
    return 0


def _post(c: AgentClients, message_id: str, **placeholders) -> None:
    try:
        c.webhook.post(render(message_id, **placeholders))
    except Exception as exc:  # the state change stands
        log.warning("webhook post failed: %s", exc)


def _tick(c: AgentClients) -> None:
    row = c.state.read()
    if row.vm_state == "out":
        row = _adopt(c, row)
    if row.vm_state == "extinguishing":
        _extinguish(c, row)
        return
    if row.vm_state == "igniting":
        row = _await_ready(c, row)
        if row is None:
            return
    if row.vm_state == "lit":
        _observe(c, row)


def _adopt(c: AgentClients, row: StateRow) -> StateRow:
    """The VM was started outside Bonfire: treat it as an ignite by the agent (spec 7, step 1)."""
    now = c.clock.now()
    row = c.state.write(begin_ignite(row, now, str(uuid.uuid4())))
    c.events.record(Event("command", "ignite", "agent", now, session_id=row.session_id, detail="adopted manual start"))
    return row


def _mark_lit(c: AgentClients, row: StateRow, now: datetime, health: str) -> StateRow:
    row.vm_state = "lit"
    row.state_since = now
    row.lock_until = None
    row.last_health = health
    row.last_heartbeat = now
    return c.state.write(row)


def _await_ready(c: AgentClients, row: StateRow) -> StateRow | None:
    """Poll is_ready within this tick's budget. Returns the lit row on success, None otherwise."""
    started = c.clock.now()
    row.last_heartbeat = started
    row = c.state.write(row)
    while True:
        now = c.clock.now()
        if c.adapter.run("is_ready", TIMEOUTS["is_ready"]).rc == 0:
            row = _mark_lit(c, row, now, "ok")
            _post(c, "ready", address=c.config.public_address)
            duration_ms = int((now - (row.session_started_at or now)).total_seconds() * 1000)
            c.events.record(Event("vm", "ready", "agent", now, session_id=row.session_id, duration_ms=duration_ms))
            return row
        if row.state_since is not None and now - row.state_since >= timedelta(minutes=c.ready_timeout_minutes):
            _mark_lit(c, row, now, "crashed")
            _post(c, "ignite_failed", ready_timeout_minutes=c.ready_timeout_minutes)
            c.events.record(Event("vm", "ignite_failed", "agent", now, session_id=row.session_id, ok=False,
                                  detail=f"not ready after {c.ready_timeout_minutes} min"))
            return None
        if (now - started).total_seconds() + c.ready_poll_seconds > c.ready_poll_budget_seconds:
            return None
        c.clock.sleep(c.ready_poll_seconds)


def _observe(c: AgentClients, row: StateRow) -> None:
    now = c.clock.now()
    cfg = c.config
    pc = c.adapter.run("player_count", TIMEOUTS["player_count"])
    count = int(pc.out.strip()) if pc.rc == 0 and pc.out.strip().isdigit() else None
    hr = c.adapter.run("health", TIMEOUTS["health"])
    health = hr.out.strip() if hr.rc == 0 and hr.out.strip() in HEALTH_VALUES else "unknown"

    previous = row.last_health
    row.last_heartbeat = now
    row.last_player_count = -1 if count is None else count
    row.last_health = health

    if previous == "ok" and health in ("degraded", "crashed"):
        _post(c, "crash")
        c.events.record(Event("game", "crash", "agent", now, session_id=row.session_id, detail=f"health {previous} -> {health}"))
    if health == "crashed" and previous in ("ok", "degraded"):
        _post(c, "crash_gave_up")
        c.events.record(Event("game", "crash_gave_up", "agent", now, session_id=row.session_id))

    if count is None:  # rule 1: unknown never extinguishes
        if row.unknown_since is None:
            row.unknown_since = now
            row.unknown_alerted = False
        elif not row.unknown_alerted and now - row.unknown_since >= timedelta(minutes=UNKNOWN_ALERT_MINUTES):
            _post(c, "unknown_alert", UNKNOWN_ALERT_MINUTES=UNKNOWN_ALERT_MINUTES)
            row.unknown_alerted = True
            c.events.record(Event("watchdog", "unknown_alert", "agent", now, session_id=row.session_id,
                                  detail=f"unknown since {row.unknown_since.strftime('%H:%M')}Z"))
        c.state.write(row)
        return
    row.unknown_since = None
    row.unknown_alerted = False

    if count > 0:
        if row.idle_since is not None and row.warnings_posted:
            _post(c, "idle_cancelled")
            c.events.record(Event("watchdog", "idle_cancelled", "agent", now, session_id=row.session_id, player_count=count))
        row.idle_since = None
        row.warnings_posted = ""
        c.state.write(row)
        return

    if row.idle_since is None:
        row.idle_since = now
    remaining = timedelta(minutes=cfg.idle_timeout_minutes) - (now - row.idle_since)
    posted = {int(x) for x in row.warnings_posted.split(",") if x}
    for w in cfg.idle_warning_minutes:
        if remaining <= timedelta(minutes=w) and w not in posted:
            _post(c, "warning", w=w)
            posted.add(w)
            c.events.record(Event("watchdog", "warning", "agent", now, session_id=row.session_id, player_count=0,
                                  detail=f"{w} min remaining"))
    row.warnings_posted = ",".join(str(w) for w in cfg.idle_warning_minutes if w in posted)
    if remaining > timedelta(0):
        c.state.write(row)
        return

    detail = f"idle {cfg.idle_timeout_minutes} min; warnings {row.warnings_posted} posted"
    row = c.state.write(begin_extinguish(row, now))
    _post(c, "idle_shutdown", idle_timeout_minutes=cfg.idle_timeout_minutes)
    c.events.record(Event("watchdog", "idle_shutdown", "agent", now, session_id=row.session_id, player_count=0, detail=detail))
    _extinguish(c, row)


def _extinguish(c: AgentClients, row: StateRow) -> None:
    """Backup and upload, clean stop, deallocate (spec 7, step 2). Nothing here blocks the deallocate."""
    now = c.clock.now()
    session = row.session_id or "no-session"
    backup = c.adapter.run("backup", TIMEOUTS["backup"])
    if backup.rc == 0:
        try:
            count = c.backup.upload(c.staging_dir, f"{session}/{now.strftime('%Y%m%dT%H%M%SZ')}")
            clear_staging(c.staging_dir)
            c.events.record(Event("vm", "backup", "agent", now, session_id=row.session_id, detail=f"{count} files uploaded"))
        except Exception as exc:
            log.warning("backup upload failed: %s", exc)
            c.events.record(Event("vm", "backup", "agent", now, session_id=row.session_id, ok=False, detail=f"upload failed: {exc}"))
    else:
        c.events.record(Event("vm", "backup", "agent", now, session_id=row.session_id, ok=False,
                              detail=f"adapter backup failed: {backup.err[-200:]}"))
    stop = c.adapter.run("stop", c.stop_grace_seconds + 60)
    if stop.rc != 0:  # decision P9
        log.error("adapter stop failed (rc %s); deallocating anyway", stop.rc)
        c.events.record(Event("vm", "deallocated", "agent", now, session_id=row.session_id, ok=False,
                              detail=f"adapter stop failed: {stop.err[-200:]}"))
    c.compute.deallocate()
