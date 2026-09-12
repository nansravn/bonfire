"""The status reply selection order from docs/contracts/discord.md."""
from __future__ import annotations

from datetime import datetime, timedelta

from bonfire.core.config import Config
from bonfire.core.discord import render
from bonfire.core.state import StateRow


def whole_minutes(delta: timedelta) -> int:
    return max(0, int(delta.total_seconds() // 60))


def hours_minutes(delta: timedelta) -> tuple[int, str]:
    minutes = whole_minutes(delta)
    return minutes // 60, f"{minutes % 60:02d}"


def status_reply(row: StateRow, now: datetime, config: Config) -> str:
    if row.vm_state == "out":
        return render("status_out")
    if row.vm_state == "igniting":
        return render("status_igniting", m=whole_minutes(now - (row.state_since or now)))
    if row.vm_state == "extinguishing":
        return render("status_extinguishing")
    h, mm = hours_minutes(now - (row.session_started_at or now))
    if row.last_health == "crashed":
        return render("status_lit_crashed")
    if row.last_player_count < 0:
        return render("status_lit_unknown", h=h, mm=mm)
    if row.last_player_count == 0:
        if row.idle_since is None:
            remaining = config.idle_timeout_minutes
        else:
            remaining = max(0, config.idle_timeout_minutes - whole_minutes(now - row.idle_since))
        return render("status_lit_idle", h=h, mm=mm, r=remaining)
    return render("status_lit", n=row.last_player_count, h=h, mm=mm)
