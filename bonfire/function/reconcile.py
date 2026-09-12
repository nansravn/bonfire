"""Architecture rule 3: bring the row in line with the VM's power state (spec 6.4)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from bonfire.core.config import Config
from bonfire.core.events import Event
from bonfire.core.state import StateRow, finish_session


@dataclass
class Reconciled:
    row: StateRow
    events: list[Event] = field(default_factory=list)
    deallocate: bool = False


def needs_power_state(row: StateRow, now: datetime) -> bool:
    """Handlers read the VM power state only for the two suspect states of rule 3."""
    if row.vm_state == "extinguishing":
        return True
    return row.vm_state == "igniting" and row.lock_expired(now)


def reconcile(row: StateRow, power_state: str, now: datetime, config: Config) -> Reconciled:
    row = row.copy()
    stale = timedelta(minutes=config.heartbeat_stale_minutes)
    if row.vm_state == "extinguishing":
        if power_state == "deallocated":
            session_id = row.session_id
            finish_session(row, now)
            return Reconciled(row, [Event("vm", "deallocated", "function", now, session_id=session_id,
                                          detail="vm observed deallocated")])
        if power_state == "running" and row.lock_expired(now):
            return Reconciled(row, [Event("vm", "deallocated", "function", now, session_id=row.session_id,
                                          ok=False, detail="agent silent; function deallocated")], deallocate=True)
    elif row.vm_state == "igniting" and row.lock_expired(now):
        if power_state == "deallocated":
            session_id = row.session_id
            row.session_started_at = None  # no hours for a session that never came up
            finish_session(row, now)
            return Reconciled(row, [Event("vm", "deallocated", "function", now, session_id=session_id, ok=False,
                                          detail="vm found deallocated while igniting")])
        if power_state == "running" and row.last_heartbeat is not None and now - row.last_heartbeat <= stale:
            row.vm_state = "lit"
            row.state_since = now
            row.lock_until = None
    return Reconciled(row)
