"""Fakes for the unit level (docs/testing.md, Fakes)."""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from bonfire.core.events import Event
from bonfire.core.state import PreconditionFailed, StateRow


class FakeClock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def now(self) -> datetime:
        return self.at

    def sleep(self, seconds: float) -> None:
        self.at += timedelta(seconds=seconds)

    def set(self, at: datetime) -> None:
        self.at = at

    def advance(self, **kwargs) -> None:
        self.at += timedelta(**kwargs)


class FakeStateTable:
    """One row with ETag semantics: a stale ETag raises PreconditionFailed."""

    def __init__(self, row: StateRow | None = None) -> None:
        self._row = (row or StateRow()).copy()
        self._etag = 1
        self.reads = 0
        self.writes: list[tuple[str | None, bool]] = []
        self.history: list[str] = [self._row.vm_state]
        self.before_write: Callable[[], None] | None = None

    def read(self) -> StateRow:
        self.reads += 1
        row = self._row.copy()
        row.etag = str(self._etag)
        return row

    def write(self, row: StateRow) -> StateRow:
        if self.before_write is not None:
            hook, self.before_write = self.before_write, None
            hook()
        if row.etag != str(self._etag):
            self.writes.append((row.etag, False))
            raise PreconditionFailed()
        self._etag += 1
        self._row = row.copy()
        self.writes.append((row.etag, True))
        self.history.append(row.vm_state)
        written = row.copy()
        written.etag = str(self._etag)
        return written

    def set(self, **fields) -> None:
        """Test setup: change fields directly (bumps the ETag like a foreign write)."""
        self._row = dataclasses.replace(self._row, **fields)
        self._etag += 1

    def current(self) -> StateRow:
        row = self._row.copy()
        row.etag = str(self._etag)
        return row


class FakeEvents:
    def __init__(self) -> None:
        self.items: list[Event] = []

    def record(self, event: Event) -> None:
        event.to_document()  # validates the shape the way the real sink would
        self.items.append(event)


class FakeWebhook:
    def __init__(self) -> None:
        self.posts: list[str] = []

    def post(self, content: str) -> None:
        self.posts.append(content)


@dataclasses.dataclass
class Edit:
    token: str
    content: str
    components: list


@dataclasses.dataclass
class FollowUp:
    token: str
    content: str
    ephemeral: bool


class FakeReplies:
    def __init__(self) -> None:
        self.edits: list[Edit] = []
        self.follow_ups: list[FollowUp] = []

    def edit_original(self, token: str, content: str, components: list | None = None) -> None:
        self.edits.append(Edit(token, content, components or []))

    def follow_up(self, token: str, content: str, ephemeral: bool = False) -> None:
        self.follow_ups.append(FollowUp(token, content, ephemeral))

    def edits_for(self, token: str) -> list[Edit]:
        return [e for e in self.edits if e.token == token]


class Signer:
    """A test Ed25519 key pair that signs payloads the way Discord does."""

    def __init__(self) -> None:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

        self._key = Ed25519PrivateKey.generate()
        self.public_key_hex = self._key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()

    def headers(self, timestamp: str, body: bytes) -> dict[str, str]:
        return {
            "X-Signature-Ed25519": self._key.sign(timestamp.encode() + body).hex(),
            "X-Signature-Timestamp": timestamp,
        }


class FakeCompute:
    """Records start and deallocate; power state is set by the test. Optionally logs deallocate to a file."""

    def __init__(self, log: Path | None = None) -> None:
        self.power = "deallocated"
        self.starts = 0
        self.deallocates = 0
        self._log = log

    def start(self) -> None:
        self.starts += 1

    def deallocate(self) -> None:
        self.deallocates += 1
        if self._log is not None:
            with self._log.open("a") as fh:
                fh.write("deallocate\n")

    def power_state(self) -> str:
        return self.power


class FakeBackupStore:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, list[str]]] = []
        self.fail = False

    def upload(self, staging_dir: Path, prefix: str) -> int:
        if self.fail:
            raise RuntimeError("blob unavailable")
        files = sorted(str(p.relative_to(staging_dir)) for p in Path(staging_dir).rglob("*") if p.is_file())
        self.uploads.append((prefix, files))
        return len(files)
