"""Fakes for the unit level (docs/testing.md, Fakes)."""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

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
