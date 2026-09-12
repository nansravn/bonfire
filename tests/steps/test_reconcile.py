"""Architecture rule 3 as a pure function (spec 6.4)."""
from datetime import datetime, timedelta, timezone

import pytest

from bonfire.core.config import Config
from bonfire.core.state import StateRow
from bonfire.function.reconcile import needs_power_state, reconcile

pytestmark = pytest.mark.unit
NOW = datetime(2026, 9, 12, 20, 0, tzinfo=timezone.utc)
CFG = Config()


def extinguishing(lock_delta):
    return StateRow(vm_state="extinguishing", session_id="s", session_started_at=NOW - timedelta(hours=3),
                    session_ended_at=NOW - timedelta(minutes=2), lock_until=NOW + lock_delta,
                    hours_this_month=10.0, hours_month="2026-09")


def test_needs_power_state_only_for_suspect_states():
    assert needs_power_state(extinguishing(timedelta(minutes=3)), NOW)
    assert needs_power_state(StateRow(vm_state="igniting", lock_until=NOW - timedelta(minutes=1)), NOW)
    assert not needs_power_state(StateRow(vm_state="igniting", lock_until=NOW + timedelta(minutes=1)), NOW)
    assert not needs_power_state(StateRow(vm_state="lit"), NOW)
    assert not needs_power_state(StateRow(vm_state="out", last_heartbeat=NOW), NOW)


def test_extinguishing_and_deallocated_becomes_out_with_hours():
    result = reconcile(extinguishing(timedelta(minutes=3)), "deallocated", NOW, CFG)
    assert result.row.vm_state == "out" and result.row.session_id is None
    assert abs(result.row.hours_this_month - 12.9667) < 0.001
    assert [e.action for e in result.events] == ["deallocated"] and result.events[0].session_id == "s"
    assert result.deallocate is False


def test_extinguishing_running_expired_lock_deallocates_without_changing_row():
    row = extinguishing(timedelta(minutes=-1))
    result = reconcile(row, "running", NOW, CFG)
    assert result.deallocate is True and result.row == row
    assert result.events[0].ok is False


def test_extinguishing_running_active_lock_is_left_alone():
    row = extinguishing(timedelta(minutes=3))
    result = reconcile(row, "running", NOW, CFG)
    assert result.row == row and not result.deallocate and result.events == []


def test_igniting_expired_lock_deallocated_becomes_out():
    row = StateRow(vm_state="igniting", session_id="s", session_started_at=NOW - timedelta(minutes=10),
                   lock_until=NOW - timedelta(minutes=5))
    result = reconcile(row, "deallocated", NOW, CFG)
    assert result.row.vm_state == "out" and result.row.session_id is None and result.row.hours_this_month == 0.0


def test_igniting_expired_lock_running_fresh_heartbeat_becomes_lit():
    row = StateRow(vm_state="igniting", session_id="s", session_started_at=NOW - timedelta(minutes=10),
                   lock_until=NOW - timedelta(minutes=1), last_heartbeat=NOW - timedelta(minutes=1))
    result = reconcile(row, "running", NOW, CFG)
    assert result.row.vm_state == "lit" and result.row.lock_until is None


def test_transitioning_power_state_changes_nothing():
    row = extinguishing(timedelta(minutes=-1))
    result = reconcile(row, "transitioning", NOW, CFG)
    assert result.row == row and not result.deallocate
