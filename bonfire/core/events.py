"""Append-only events in Cosmos (docs/contracts/data-schema.md, events)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from bonfire.core.clock import iso

ALLOWED_ACTIONS = {
    "command": {"ignite", "extinguish", "check", "cost", "restart", "keep_lit"},
    "vm": {"ready", "ignite_failed", "deallocated", "backup"},
    "watchdog": {"warning", "idle_cancelled", "idle_shutdown", "unknown_alert", "ceiling_warning",
                 "ceiling", "heartbeat_missing", "boot_failed"},
    "game": {"crash", "crash_gave_up"},
}


@dataclass
class Event:
    type: str
    action: str
    actor: str
    ts: datetime
    session_id: str | None = None
    player_count: int | None = None
    duration_ms: int | None = None
    ok: bool = True
    detail: str = ""

    def __post_init__(self) -> None:
        if self.action not in ALLOWED_ACTIONS.get(self.type, ()):
            raise ValueError(f"unknown event {self.type}/{self.action}")

    def to_document(self) -> dict[str, Any]:
        return {
            "id": str(uuid.uuid4()),
            "month": self.ts.strftime("%Y-%m"),
            "ts": iso(self.ts),
            "session_id": self.session_id,
            "type": self.type,
            "action": self.action,
            "actor": self.actor,
            "player_count": self.player_count,
            "duration_ms": self.duration_ms,
            "ok": self.ok,
            "detail": self.detail[:500],
        }


class EventSink(Protocol):
    def record(self, event: Event) -> None: ...


class CosmosEventSink:
    def __init__(self, endpoint: str, credential: Any, database: str = "bonfire", container: str = "events") -> None:
        from azure.cosmos import CosmosClient

        self._container = CosmosClient(endpoint, credential).get_database_client(database).get_container_client(container)

    def record(self, event: Event) -> None:
        self._container.create_item(event.to_document())
