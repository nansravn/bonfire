"""Fixtures for the Valheim adapter conformance tests.

The real container is expensive to bring to "ready" (SteamCMD downloads about
1 GB the first time), so the game state is session-scoped and reused across
scenarios. Scenarios that stop the game restart it lazily through ensure_ready().
"""
import json
import os
import pathlib
import subprocess
import sys
import time
from dataclasses import dataclass

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
ADAPTER_DIR = REPO / "games" / "valheim"
IMAGE = "lloesche/valheim-server:latest"
CONTAINER = "bonfire-test-valheim-1"
WORLD = "bonfiretest"


def pytest_collection_modifyitems(items):
    if os.environ.get("BONFIRE_E2E"):
        return
    skip = pytest.mark.skip(reason="e2e scenarios run on the pilot VM; set BONFIRE_E2E=1")
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip)


@dataclass
class Result:
    rc: int
    out: str
    err: str
    seconds: float


class Adapter:
    def __init__(self, env: dict[str, str]):
        self.env = env
        self.last: Result | None = None

    def run(self, sub: str, timeout: int = 900) -> Result:
        start = time.monotonic()
        proc = subprocess.run(
            [str(ADAPTER_DIR / "adapter.sh"), sub],
            env={**os.environ, **self.env},
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        self.last = Result(proc.returncode, proc.stdout, proc.stderr, time.monotonic() - start)
        return self.last

    # Docker helpers -------------------------------------------------------
    @staticmethod
    def container_state() -> tuple[str, int] | None:
        proc = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Status}} {{.RestartCount}}", CONTAINER],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            return None
        status, restarts = proc.stdout.split()
        return status, int(restarts)

    @staticmethod
    def image_present() -> bool:
        return subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode == 0

    def a2s_answers(self) -> bool:
        import a2s  # from python-a2s
        try:
            a2s.info(("127.0.0.1", 2457), timeout=3.0)
            return True
        except Exception:
            return False

    def ensure_started(self) -> None:
        state = self.container_state()
        if state is None or state[0] != "running":
            assert self.run("start", timeout=180).rc == 0, self.last.err

    def ensure_ready(self, limit: int = 900) -> None:
        self.ensure_started()
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            if self.run("is_ready", timeout=15).rc == 0:
                return
            time.sleep(10)
        raise AssertionError(f"game not ready after {limit}s; last stderr: {self.last.err}")

    def worlds_dir(self) -> pathlib.Path:
        return pathlib.Path(self.env["BONFIRE_DATA_DIR"]) / "config" / "worlds_local"

    def world_files(self) -> list[pathlib.Path]:
        d = self.worlds_dir()
        return [d / f"{WORLD}.db", d / f"{WORLD}.fwl"]


@pytest.fixture(scope="session")
def adapter(tmp_path_factory) -> Adapter:
    data = tmp_path_factory.mktemp("data")
    backup = tmp_path_factory.mktemp("backup")
    run_dir = tmp_path_factory.mktemp("run")
    meta = json.loads((ADAPTER_DIR / "adapter.json").read_text())
    env_file = tmp_path_factory.mktemp("etc") / "valheim.env"
    env_file.write_text(
        "SERVER_NAME=bonfire-test\n"
        f"WORLD_NAME={WORLD}\n"
        "SERVER_PASS=testpass1\n"
        "SERVER_PUBLIC=true\n"
    )
    env = {
        "BONFIRE_GAME": "valheim",
        "BONFIRE_ADAPTER_DIR": str(ADAPTER_DIR),
        "BONFIRE_DATA_DIR": str(data),
        "BONFIRE_BACKUP_DIR": str(backup),
        "BONFIRE_STOP_GRACE_SECONDS": str(meta["stop_grace_seconds"]),
        "BONFIRE_GAME_ENV_FILE": str(env_file),
        "BONFIRE_PYTHON": sys.executable,
        "BONFIRE_RUN_DIR": str(run_dir),
        "COMPOSE_PROJECT_NAME": "bonfire-test",
    }
    (data / "config").mkdir()
    (data / "server").mkdir()
    a = Adapter(env)
    yield a
    a.run("stop", timeout=300)
