"""Step definitions for tests/features/adapter-valheim.feature (contract level)."""
import json
import os
import pathlib
import subprocess
import time

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from conftest import ADAPTER_DIR, CONTAINER, IMAGE, WORLD

scenarios("adapter-valheim.feature")


# Background ---------------------------------------------------------------
@given('BONFIRE_GAME is "valheim"')
def _(adapter):
    assert adapter.env["BONFIRE_GAME"] == "valheim"


@given("BONFIRE_ADAPTER_DIR is the games/valheim directory")
def _(adapter):
    assert pathlib.Path(adapter.env["BONFIRE_ADAPTER_DIR"]) == ADAPTER_DIR


@given("BONFIRE_DATA_DIR is an empty temporary directory")
def _(adapter):
    assert pathlib.Path(adapter.env["BONFIRE_DATA_DIR"]).is_dir()


@given("BONFIRE_BACKUP_DIR is an empty temporary directory")
def _(adapter):
    assert pathlib.Path(adapter.env["BONFIRE_BACKUP_DIR"]).is_dir()


@given("BONFIRE_STOP_GRACE_SECONDS is 60, copied from adapter.json")
def _(adapter):
    assert adapter.env["BONFIRE_STOP_GRACE_SECONDS"] == "60"


@given("the valheim server password is provided in the environment")
def _(adapter):
    assert "SERVER_PASS=" in pathlib.Path(adapter.env["BONFIRE_GAME_ENV_FILE"]).read_text()


# adapter.json -------------------------------------------------------------
@given("the games/valheim directory", target_fixture="meta_path")
def _():
    return ADAPTER_DIR / "adapter.json"


@when("adapter.json is parsed", target_fixture="meta")
def _(meta_path):
    return json.loads(meta_path.read_text())


@then("ports contains 2456/udp only")
def _(meta):
    assert meta["ports"] == [{"port": 2456, "proto": "udp"}]


@then("stop_grace_seconds is 60 and ready_timeout_minutes is 10")
def _(meta):
    assert meta["stop_grace_seconds"] == 60
    assert meta["ready_timeout_minutes"] == 10


# Givens about container and image ----------------------------------------
@given("the image is not present locally")
def _(adapter):
    adapter.run("stop", timeout=300)
    subprocess.run(["docker", "image", "rm", "-f", IMAGE], capture_output=True)
    assert not adapter.image_present()


@given("the image is present locally")
def _(adapter):
    if not adapter.image_present():
        assert adapter.run("install").rc == 0, adapter.last.err


@given("the container started 5 seconds ago")
def _(adapter):
    adapter.run("stop", timeout=300)
    assert adapter.run("start", timeout=180).rc == 0, adapter.last.err
    time.sleep(5)


@given("the container is running and A2S on 127.0.0.1:2457 answers")
def _(adapter):
    adapter.ensure_ready()
    assert adapter.a2s_answers()


@given("the game is ready")
def _(adapter):
    adapter.ensure_ready()


@given("the container is stopped")
def _(adapter):
    assert adapter.run("stop", timeout=300).rc == 0, adapter.last.err
    assert adapter.container_state() is None


@given("the game process was killed and Docker is restarting the container")
def _(adapter):
    adapter.ensure_started()
    before = adapter.container_state()[1]
    # Docker treats `docker kill` as a manual stop and ignores the restart policy, so
    # switch the policy to `always` and stop the container's init from inside: Docker
    # then restarts it and RestartCount grows, which is what health observes.
    subprocess.run(["docker", "update", "--restart=always", CONTAINER], check=True, capture_output=True)
    try:
        stop = subprocess.run(["docker", "exec", CONTAINER, "supervisorctl", "shutdown"], capture_output=True)
        if stop.returncode != 0:
            subprocess.run(["docker", "exec", CONTAINER, "kill", "-TERM", "1"], check=True, capture_output=True)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            state = adapter.container_state()
            if state and state[1] > before:
                return
            time.sleep(2)
        raise AssertionError("Docker did not restart the container within 180 s")
    finally:
        subprocess.run(["docker", "update", "--restart=on-failure:3", CONTAINER], capture_output=True)


@given("the container has exited after three failed restarts")
def _(adapter):
    # Simulates Docker giving up (decision P7): stop restarting, then kill.
    adapter.ensure_started()
    subprocess.run(["docker", "update", "--restart=no", CONTAINER], check=True, capture_output=True)
    subprocess.run(["docker", "kill", "--signal=KILL", CONTAINER], check=True, capture_output=True)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        state = adapter.container_state()
        if state and state[0] == "exited":
            return
        time.sleep(1)
    raise AssertionError("container did not reach exited")


@given("the game is ready and a world file exists in BONFIRE_DATA_DIR", target_fixture="stop_began")
def _(adapter):
    adapter.ensure_ready()
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline and not adapter.world_files():
        time.sleep(5)
    assert adapter.world_files(), "no world file after 5 min"
    return time.time()


@given("a world file exists in BONFIRE_DATA_DIR")
def _(adapter):
    if not adapter.world_files():
        adapter.ensure_ready()
        assert adapter.run("stop", timeout=300).rc == 0  # a clean stop writes the world out
    assert adapter.world_files()


# Whens --------------------------------------------------------------------
@when(parsers.parse('"adapter.sh {sub}" runs'), target_fixture="result")
def _(adapter, sub):
    return adapter.run(sub)


@when("each subcommand in the contract runs", target_fixture="results")
def _(adapter):
    order = ["install", "start", "is_ready", "player_count", "health", "backup", "stop"]
    return {sub: adapter.run(sub) for sub in order}


# Thens --------------------------------------------------------------------
@then(parsers.parse("it exits {code:d} within {n:d} minutes"))
def _(result, code, n):
    assert result.rc == code, result.err
    assert result.seconds <= n * 60


@then(parsers.parse("it exits {code:d} within {n:d} seconds"))
def _(result, code, n):
    assert result.rc == code, result.err
    assert result.seconds <= n


@then(parsers.parse('it exits 0 and prints exactly "{value}"'))
def _(result, value):
    assert result.rc == 0, result.err
    assert result.out == value + "\n"


@then("the image is present locally")
def _(adapter):
    assert adapter.image_present()


@then("a container for the adapter is running")
def _(adapter):
    state = adapter.container_state()
    assert state and state[0] == "running"


@then("no container for the adapter is running")
def _(adapter):
    state = adapter.container_state()
    assert state is None or state[0] != "running"


@then("the world file was modified after stop began")
def _(adapter, stop_began):
    assert any(p.stat().st_mtime >= stop_began - 1 for p in adapter.world_files())


@then("BONFIRE_BACKUP_DIR contains a copy of every world file")
def _(adapter):
    runs = sorted(pathlib.Path(adapter.env["BONFIRE_BACKUP_DIR"]).iterdir())
    assert runs, "no backup directory created"
    run = runs[-1]
    for src in adapter.world_files():
        copy = run / src.relative_to(adapter.worlds_dir())
        assert copy.exists() and copy.stat().st_size == src.stat().st_size


@then("stdout contains nothing beyond the value the contract specifies")
def _(results):
    for sub in ("install", "start", "is_ready", "backup", "stop"):
        assert results[sub].out == "", f"{sub} wrote to stdout: {results[sub].out!r}"
    pc = results["player_count"].out.strip()
    assert pc == "unknown" or pc.isdigit()
    assert results["health"].out.strip() in {"ok", "degraded", "crashed"}
    for sub, r in results.items():
        assert r.out.count("\n") <= 1, f"{sub} printed more than one line"
