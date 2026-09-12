"""State row conversion, transitions and ETag semantics (docs/contracts/data-schema.md)."""
from datetime import datetime, timedelta, timezone

import pytest

from bonfire.core.state import PreconditionFailed, StateRow, begin_extinguish, begin_ignite, finish_session
from fakes import FakeStateTable

pytestmark = pytest.mark.unit
NOW = datetime(2026, 9, 12, 20, 0, tzinfo=timezone.utc)


def test_entity_omits_nulls_and_round_trips():
    row = StateRow(vm_state="lit", session_id="s1", session_started_at=NOW, last_player_count=2, hours_this_month=1.5, hours_month="2026-09")
    entity = row.to_entity()
    assert entity["PartitionKey"] == "bonfire" and entity["RowKey"] == "state"
    assert "idle_since" not in entity and "lock_until" not in entity
    assert entity["warnings_posted"] == "" and entity["unknown_alerted"] is False
    assert StateRow.from_entity(entity) == row


def test_from_entity_defaults_missing_properties():
    row = StateRow.from_entity({"PartitionKey": "bonfire", "RowKey": "state", "vm_state": "out"})
    assert row == StateRow()
    assert row.last_player_count == -1 and row.last_health == "unknown"


def test_begin_ignite_sets_session_and_lock():
    row = begin_ignite(StateRow(last_heartbeat=NOW - timedelta(hours=5)), NOW, "sess")
    assert row.vm_state == "igniting" and row.session_id == "sess"
    assert row.session_started_at == NOW and row.state_since == NOW
    assert row.lock_until == NOW + timedelta(minutes=5)
    assert row.last_heartbeat is None and row.ceiling_warned is False


def test_begin_extinguish_clears_idle_fields():
    row = StateRow(vm_state="lit", idle_since=NOW, warnings_posted="15", session_id="s")
    begin_extinguish(row, NOW)
    assert row.vm_state == "extinguishing" and row.session_ended_at == NOW
    assert row.idle_since is None and row.warnings_posted == ""
    assert row.lock_until == NOW + timedelta(minutes=5)


def test_finish_session_adds_hours_and_rolls_month():
    row = StateRow(vm_state="extinguishing", session_id="s", session_started_at=NOW - timedelta(hours=3),
                   session_ended_at=NOW - timedelta(minutes=2), hours_this_month=10.0, hours_month="2026-08",
                   lock_until=NOW)
    finish_session(row, NOW)
    assert row.vm_state == "out" and row.session_id is None and row.lock_until is None
    assert row.hours_month == "2026-09" and abs(row.hours_this_month - 2.9667) < 0.001


def test_fake_table_rejects_stale_etag():
    table = FakeStateTable()
    a = table.read()
    b = table.read()
    a.vm_state = "igniting"
    table.write(a)
    b.vm_state = "extinguishing"
    with pytest.raises(PreconditionFailed):
        table.write(b)
    assert table.current().vm_state == "igniting"
    assert table.writes == [(a.etag, True), (b.etag, False)]
    assert table.history == ["out", "igniting"]
