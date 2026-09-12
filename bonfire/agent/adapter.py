"""Run adapter.sh subcommands with the contract's timeouts (docs/contracts/adapter-interface.md)."""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

TIMEOUTS = {"install": 900, "start": 120, "is_ready": 10, "player_count": 10, "health": 10, "backup": 300}


@dataclass
class AdapterResult:
    rc: int
    out: str
    err: str
    timed_out: bool = False


class Adapter(Protocol):
    def run(self, subcommand: str, timeout: float) -> AdapterResult: ...


class ShellAdapter:
    def __init__(self, adapter_dir: Path, env: Mapping[str, str]) -> None:
        self._dir = Path(adapter_dir)
        self._env = dict(env)

    def run(self, subcommand: str, timeout: float) -> AdapterResult:
        try:
            proc = subprocess.run(
                [str(self._dir / "adapter.sh"), subcommand],
                cwd=self._dir, env={**os.environ, **self._env},
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            return AdapterResult(-1, exc.stdout or "", exc.stderr or "", timed_out=True)
        return AdapterResult(proc.returncode, proc.stdout, proc.stderr)


def load_adapter_meta(adapter_dir: Path) -> dict:
    return json.loads((Path(adapter_dir) / "adapter.json").read_text())
