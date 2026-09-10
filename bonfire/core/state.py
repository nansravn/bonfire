"""The one operational state row (docs/contracts/data-schema.md) and its transitions."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from bonfire.core.clock import utc
from bonfire.core.config import LOCK_TTL_MINUTES

PARTITION_KEY = "bonfire"
ROW_KEY = "state"
VM_STATES = ("out", "igniting", "lit", "extinguishing")
_DATETIMES = ("state_since", "session_started_at", "session_ended_at", "idle_since",
              "unknown_since", "last_heartbeat", "lock_until")


class PreconditionFailed(Exception):
    """The row changed since it was read (HTTP 412)."""


@dataclass
class StateRow:
    vm_state: str = "out"
    state_since: datetime | None = None
    session_id: str | None = None
    session_started_at: datetime | None = None
    session_ended_at: datetime | None = None
    idle_since: datetime | None = None
    warnings_posted: str = ""
    unknown_since: datetime | None = None
    unknown_alerted: bool = False
    last_heartbeat: datetime | None = None
    last_player_count: int = -1
    last_health: str = "unknown"
    ceiling_warned: bool = False
    pending_command: str | None = None
    hours_this_month: float = 0.0
    hours_month: str = ""
    lock_until: datetime | None = None
    etag: str | None = field(default=None, compare=False)

    def copy(self) -> "StateRow":
        return dataclasses.replace(self)

    def to_entity(self) -> dict[str, Any]:
        entity: dict[str, Any] = {"PartitionKey": PARTITION_KEY, "RowKey": ROW_KEY}
        for f in dataclasses.fields(self):
            if f.name == "etag":
                continue
            value = getattr(self, f.name)
            if value is None:
                continue
            entity[f.name] = utc(value) if isinstance(value, datetime) else value
        return entity

    @classmethod
    def from_entity(cls, entity: dict[str, Any]) -> "StateRow":
        kwargs: dict[str, Any] = {}
        for f in dataclasses.fields(cls):
            if f.name == "etag" or f.name not in entity:
                continue
            value = entity[f.name]
            if f.name in _DATETIMES and value is not None:
                value = utc(datetime(value.year, value.month, value.day, value.hour, value.minute,
                                     value.second, value.microsecond, tzinfo=value.tzinfo))
            if f.name == "last_player_count":
                value = int(value)
            if f.name == "hours_this_month":
                value = float(value)
            kwargs[f.name] = value
        return cls(**kwargs)

    def lock_expired(self, now: datetime) -> bool:
        return self.lock_until is None or self.lock_until <= now


class StateTable(Protocol):
    def read(self) -> StateRow: ...
    def write(self, row: StateRow) -> StateRow: ...


def begin_ignite(row: StateRow, now: datetime, session_id: str) -> StateRow:
    row.vm_state = "igniting"
    row.state_since = now
    row.session_id = session_id
    row.session_started_at = now
    row.session_ended_at = None
    row.idle_since = None
    row.warnings_posted = ""
    row.unknown_since = None
    row.unknown_alerted = False
    row.last_heartbeat = None
    row.last_player_count = -1
    row.last_health = "unknown"
    row.ceiling_warned = False
    row.pending_command = None
    row.lock_until = now + timedelta(minutes=LOCK_TTL_MINUTES)
    return row


def begin_extinguish(row: StateRow, now: datetime) -> StateRow:
    row.vm_state = "extinguishing"
    row.state_since = now
    row.session_ended_at = now
    row.idle_since = None
    row.warnings_posted = ""
    row.pending_command = None
    row.lock_until = now + timedelta(minutes=LOCK_TTL_MINUTES)
    return row


def finish_session(row: StateRow, now: datetime) -> StateRow:
    """extinguishing -> out: add the session's hours (rolling the month) and clear session fields."""
    month = now.strftime("%Y-%m")
    if row.hours_month != month:
        row.hours_this_month = 0.0
        row.hours_month = month
    if row.session_started_at and row.session_ended_at:
        row.hours_this_month += (row.session_ended_at - row.session_started_at).total_seconds() / 3600
    row.vm_state = "out"
    row.state_since = now
    row.session_id = None
    row.session_started_at = None
    row.session_ended_at = None
    row.idle_since = None
    row.warnings_posted = ""
    row.unknown_since = None
    row.unknown_alerted = False
    row.pending_command = None
    row.lock_until = None
    return row


class AzureStateTable:
    """Table Storage client: Replace with If-Match; the row is created on first read."""

    def __init__(self, endpoint: str, credential: Any, table_name: str = "state") -> None:
        from azure.data.tables import TableClient

        self._client = TableClient(endpoint=endpoint, table_name=table_name, credential=credential)

    def read(self) -> StateRow:
        from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError

        try:
            entity = self._client.get_entity(PARTITION_KEY, ROW_KEY)
        except ResourceNotFoundError:
            try:
                self._client.create_entity(StateRow().to_entity())
            except ResourceExistsError:
                pass
            entity = self._client.get_entity(PARTITION_KEY, ROW_KEY)
        row = StateRow.from_entity(dict(entity))
        row.etag = entity.metadata["etag"]
        return row

    def write(self, row: StateRow) -> StateRow:
        from azure.core import MatchConditions
        from azure.core.exceptions import ResourceModifiedError
        from azure.data.tables import UpdateMode

        try:
            meta = self._client.update_entity(
                row.to_entity(), mode=UpdateMode.REPLACE, etag=row.etag,
                match_condition=MatchConditions.IfNotModified,
            )
        except ResourceModifiedError as exc:
            raise PreconditionFailed() from exc
        written = row.copy()
        written.etag = meta["etag"]
        return written
