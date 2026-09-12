"""Shared World fixture and step definitions for the six unit feature files (decisions P1, P2, P10)."""
from __future__ import annotations

import dataclasses
import json
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, then, when

from bonfire.agent.adapter import ShellAdapter
from bonfire.core.config import UNKNOWN_ALERT_MINUTES, Config
from bonfire.core.discord import mention, render
from bonfire.core.state import StateRow
from fakes import (FakeBackupStore, FakeClock, FakeCompute, FakeEvents, FakeReplies, FakeStateTable,
                   FakeWebhook, Signer)

REPO = Path(__file__).resolve().parents[2]
FAKE_ADAPTER_DIR = REPO / "tests" / "fake-adapter"
BASE_NOW = datetime(2026, 9, 12, 20, 0, tzinfo=timezone.utc)
MEMBERS = {"member": "100000000000000001", "A": "100000000000000002",
           "B": "100000000000000003", "different": "100000000000000004"}
_SPAN = r"\d+ (?:hours?|minutes?|seconds?)(?: \d+ (?:hours?|minutes?|seconds?))*"
REL = rf"(?:{_SPAN} (?:ago|ahead|in the past)|null|now)"
DUR = _SPAN
_UNIT = {"hour": 3600, "minute": 60, "second": 1}
# Placeholder lists look like `n 3, h 1, mm 20`; the strict shape keeps longer phrases from matching.
KV = r"\w+ [^,\s]+(?:, \w+ [^,\s]+)*"


def duration(text: str) -> timedelta:
    seconds = sum(int(n) * _UNIT[u.rstrip("s")] for n, u in re.findall(r"(\d+) (hours?|minutes?|seconds?)", text))
    return timedelta(seconds=seconds)


def rel(text: str, now: datetime) -> datetime | None:
    text = text.strip()
    if text == "null":
        return None
    if text == "now":
        return now
    if text.endswith("ahead"):
        return now + duration(text)
    return now - duration(text)


def placeholders(text: str | None) -> dict[str, str]:
    return {k: v.strip() for k, v in re.findall(r"(\w+) ([^,]+)", text or "")}


class World:
    def __init__(self, tmp_path: Path) -> None:
        self.clock = FakeClock(BASE_NOW)
        self.config = Config(
            public_address="203.0.113.10:2456",
            vm_resource_id="/subscriptions/s/resourceGroups/rg-bonfire-pilot/providers/Microsoft.Compute/virtualMachines/vm-bonfire",
        )
        self.table = FakeStateTable()
        self.events = FakeEvents()
        self.compute_fn = FakeCompute()
        self.fake_log = tmp_path / "fake.log"
        self.compute_agent = FakeCompute(log=self.fake_log)
        self.webhook = FakeWebhook()
        self.replies = FakeReplies()
        self.backup = FakeBackupStore()
        self.staging = tmp_path / "staging"
        self.staging.mkdir()
        self.adapter_env: dict[str, str] = {"FAKE_LOG": str(self.fake_log)}
        self.signer = Signer()
        self.tokens: dict[str, str] = {}
        self.last_http = None
        self.http_seconds = 0.0
        self.snapshot: StateRow | None = None
        self._n = 0

    # configuration and row ------------------------------------------------
    def set_config(self, **kw) -> None:
        self.config = dataclasses.replace(self.config, **kw)

    def now(self) -> datetime:
        return self.clock.now()

    def row(self) -> StateRow:
        return self.table.current()

    def set_row(self, **fields) -> None:
        self.table.set(**fields)

    def set_power(self, state: str) -> None:
        """Both fake compute clients see the same VM."""
        self.compute_fn.power = state
        self.compute_agent.power = state

    def calls(self) -> list[str]:
        return self.fake_log.read_text().split() if self.fake_log.exists() else []

    def defaults(self) -> dict:
        return {
            "user": mention(MEMBERS["member"]),
            "address": self.config.public_address,
            "idle_timeout_minutes": self.config.idle_timeout_minutes,
            "UNKNOWN_ALERT_MINUTES": UNKNOWN_ALERT_MINUTES,
            "ready_timeout_minutes": 5,
            "max_session_hours": self.config.max_session_hours,
            "heartbeat_stale_minutes": self.config.heartbeat_stale_minutes,
        }

    def expect(self, message_id: str, kv: str | None = None, **extra) -> str:
        return render(message_id, **{**self.defaults(), **extra, **placeholders(kv)})

    # clients (lazy imports: decision P2) ----------------------------------
    def function_clients(self):
        from bonfire.function.worker import Clients

        return Clients(config=self.config, clock=self.clock, state=self.table, events=self.events,
                       compute=self.compute_fn, webhook=self.webhook, replies=self.replies)

    def agent_clients(self):
        from bonfire.agent.check import AgentClients

        return AgentClients(config=self.config, clock=self.clock, state=self.table, events=self.events,
                            compute=self.compute_agent, webhook=self.webhook,
                            adapter=ShellAdapter(FAKE_ADAPTER_DIR, self.adapter_env), backup=self.backup,
                            staging_dir=self.staging, ready_timeout_minutes=5, stop_grace_seconds=1)

    # actions ---------------------------------------------------------------
    def _interaction(self, member: str, sub: str | None = None, custom_id: str | None = None) -> dict:
        self._n += 1
        token = f"tok-{member}-{self._n}"
        self.tokens[member] = token
        base = {"token": token, "application_id": "app", "member": {"user": {"id": MEMBERS[member]}}}
        if sub is not None:
            return {**base, "type": 2, "data": {"name": "bonfire", "options": [{"type": 1, "name": sub}]}}
        return {**base, "type": 3, "data": {"custom_id": custom_id, "component_type": 2}}

    def _deliver(self, interaction: dict) -> None:
        from bonfire.function.interactions import handle_http
        from bonfire.function.worker import handle_interaction

        self.snapshot = self.row()
        body = json.dumps(interaction).encode()
        timestamp = str(int(self.now().timestamp()))
        started = time.monotonic()
        self.last_http = handle_http(self.signer.headers(timestamp, body), body, self.signer.public_key_hex, self.now())
        self.http_seconds = time.monotonic() - started
        assert self.last_http.queue_message, self.last_http
        handle_interaction(json.loads(self.last_http.queue_message), self.function_clients())

    def run_command(self, sub: str, member: str = "member") -> None:
        self._deliver(self._interaction(member, sub=sub))

    def click(self, label: str, member: str) -> None:
        for edit in reversed(self.replies.edits):
            for row in edit.components:
                for button in row.get("components", []):
                    if button["label"] == label:
                        self._deliver(self._interaction(member, custom_id=button["custom_id"]))
                        return
        raise AssertionError(f"no button labelled {label} was shown")

    def run_agent(self) -> None:
        from bonfire.agent.check import run_check

        self.snapshot = self.row()
        run_check(self.agent_clients())

    def run_watchdog(self) -> None:
        from bonfire.function.watchdog import run_watchdog

        self.snapshot = self.row()
        run_watchdog(self.function_clients())

    # observations ---------------------------------------------------------
    def reply_for(self, member: str) -> str:
        return self.replies.edits_for(self.tokens[member])[-1].content

    def last_reply(self) -> str:
        assert self.replies.edits, "no reply was edited"
        return self.replies.edits[-1].content

    def events_of(self, type_: str, action: str) -> list:
        return [e for e in self.events.items if e.type == type_ and e.action == action]


@pytest.fixture
def w(tmp_path: Path) -> World:
    return World(tmp_path)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
@given(parsers.re(r"^(?P<name>idle_timeout_minutes|idle_check_interval|max_session_hours|heartbeat_stale_minutes) is (?P<value>\d+)$"))
def _(w, name, value):
    w.set_config(**{name: int(value)})


@given(parsers.parse('idle_warning_minutes is "{values}"'))
def _(w, values):
    w.set_config(idle_warning_minutes=tuple(int(x) for x in values.split(",")))


@given('the configured game is "valheim"')
def _(w):
    assert w.config.game == "valheim"


@given(parsers.parse("the adapter declares ready_timeout_minutes {n:d}"))
def _(w, n):
    assert json.loads((FAKE_ADAPTER_DIR / "adapter.json").read_text())["ready_timeout_minutes"] == n


# ---------------------------------------------------------------------------
# The bonfire is ... (row setup)
# ---------------------------------------------------------------------------
def _session(w, started: datetime) -> dict:
    return {"session_id": str(uuid.uuid4()), "session_started_at": started, "hours_month": w.now().strftime("%Y-%m")}


def _lit(w, started: datetime, players: int = 0, health: str = "ok") -> None:
    w.set_power("running")
    w.set_row(vm_state="lit", state_since=started + timedelta(minutes=1), last_heartbeat=w.now() - timedelta(minutes=1),
              last_player_count=players, last_health=health, lock_until=None, idle_since=None, warnings_posted="",
              **_session(w, started))


@given("the bonfire is out")
def _(w):
    w.set_power("deallocated")
    w.set_row(vm_state="out", state_since=w.now() - timedelta(hours=8), session_id=None, session_started_at=None,
              session_ended_at=None, lock_until=None, last_heartbeat=w.now() - timedelta(hours=8))


@given("the bonfire is igniting")
def _(w):
    since = w.now() - timedelta(minutes=1)
    w.set_power("running")
    w.set_row(vm_state="igniting", state_since=since, lock_until=since + timedelta(minutes=5), last_heartbeat=None,
              last_player_count=-1, last_health="unknown", **_session(w, since))


@given(parsers.re(rf"^the bonfire is igniting since (?P<when>{REL})$"))
def _(w, when):
    since = rel(when, w.now())
    w.set_power("running")
    w.set_row(vm_state="igniting", state_since=since, lock_until=since + timedelta(minutes=5), last_heartbeat=None,
              last_player_count=-1, last_health="unknown", **_session(w, since))


@given(parsers.re(rf"^the bonfire is igniting with lock_until (?P<when>{REL})$"))
def _(w, when):
    lock = rel(when, w.now())
    since = lock - timedelta(minutes=5)
    w.set_power("running")
    w.set_row(vm_state="igniting", state_since=since, lock_until=lock, last_heartbeat=None,
              last_player_count=-1, last_health="unknown", **_session(w, since))


@given("the bonfire is lit")
def _(w):
    _lit(w, w.now() - timedelta(hours=1))


@given(parsers.parse("the bonfire is lit with {n:d} players online"))
def _(w, n):
    _lit(w, w.now() - timedelta(hours=1), players=n)


@given(parsers.re(rf"^the bonfire is lit with (?P<n>\d+) players online, lit for (?P<dur>{DUR})$"))
def _(w, n, dur):
    _lit(w, w.now() - duration(dur), players=int(n))


@given("the bonfire is lit and the last player count is unknown")
def _(w):
    _lit(w, w.now() - timedelta(hours=1), players=-1)


@given(parsers.parse('the bonfire is lit and last_health is "{health}"'))
def _(w, health):
    _lit(w, w.now() - timedelta(hours=1), health=health)


@given(parsers.re(rf"^the bonfire is lit with session_started_at (?P<when>{REL})$"))
def _(w, when):
    _lit(w, rel(when, w.now()))


@given("the bonfire is extinguishing")
def _(w):
    ended = w.now() - timedelta(minutes=1)
    w.set_power("running")
    w.set_row(vm_state="extinguishing", state_since=ended, session_ended_at=ended, lock_until=ended + timedelta(minutes=5),
              last_heartbeat=ended, last_player_count=0, last_health="ok", idle_since=None, warnings_posted="",
              **_session(w, w.now() - timedelta(hours=2)))


@given(parsers.re(rf"^the bonfire is extinguishing with lock_until (?P<when>{REL})$"))
def _(w, when):
    lock = rel(when, w.now())
    ended = lock - timedelta(minutes=5)
    w.set_power("running")
    w.set_row(vm_state="extinguishing", state_since=ended, session_ended_at=ended, lock_until=lock,
              last_heartbeat=ended, last_player_count=0, last_health="ok", **_session(w, w.now() - timedelta(hours=2)))


@given(parsers.re(rf"^the bonfire is extinguishing with session_started_at (?P<started>{REL}) and session_ended_at (?P<ended>{REL})$"))
def _(w, started, ended):
    ended_at = rel(ended, w.now())
    w.set_power("running")
    w.set_row(vm_state="extinguishing", state_since=ended_at, session_ended_at=ended_at,
              lock_until=ended_at + timedelta(minutes=5), last_heartbeat=ended_at, last_player_count=0,
              last_health="ok", **_session(w, rel(started, w.now())))


# ---------------------------------------------------------------------------
# Row fields (Given = set)
# ---------------------------------------------------------------------------
@given(parsers.re(rf"^idle_since is (?P<when>{REL})$"))
def _(w, when):
    w.set_row(idle_since=rel(when, w.now()))


@given(parsers.re(rf'^idle_since is (?P<when>{REL}) and warnings_posted is "(?P<posted>[^"]*)"$'))
def _(w, when, posted):
    w.set_row(idle_since=rel(when, w.now()), warnings_posted=posted)


@given(parsers.re(rf'^the state row has idle_since (?P<when>{REL}) and warnings_posted "(?P<posted>[^"]*)"$'))
def _(w, when, posted):
    w.set_row(idle_since=rel(when, w.now()), warnings_posted=posted)


@given(parsers.re(rf"^unknown_since is (?P<when>{REL})$"))
def _(w, when):
    w.set_row(unknown_since=rel(when, w.now()), last_player_count=-1)


@given(parsers.re(rf"^unknown_since is (?P<when>{REL}) and unknown_alerted is (?P<flag>true|false)$"))
def _(w, when, flag):
    w.set_row(unknown_since=rel(when, w.now()), unknown_alerted=flag == "true", last_player_count=-1)


@given(parsers.re(rf"^last_heartbeat is (?P<when>{REL})$"))
def _(w, when):
    w.set_row(last_heartbeat=rel(when, w.now()))


@given(parsers.re(rf"^last_heartbeat is (?P<when>{REL}) and ceiling_warned is (?P<flag>true|false)$"))
def _(w, when, flag):
    w.set_row(last_heartbeat=rel(when, w.now()), ceiling_warned=flag == "true")


@given(parsers.re(rf"^last_heartbeat is (?P<when>{REL}) and last_player_count is (?P<n>\d+)$"))
def _(w, when, n):
    w.set_row(last_heartbeat=rel(when, w.now()), last_player_count=int(n))


@given(parsers.parse('last_health is "{health}"'))
def _(w, health):
    w.set_row(last_health=health)


@given(parsers.parse("hours_this_month is {hours:g} for the current month"))
def _(w, hours):
    w.set_row(hours_this_month=float(hours), hours_month=w.now().strftime("%Y-%m"))


@given(parsers.parse("the VM power state is {state}"))
def _(w, state):
    w.set_power(state)  # overrides the default the "the bonfire is ..." step chose


@given("the agent process has just started with no memory of earlier checks")
def _(w):
    pass  # every tick is a fresh process; nothing to reset


# ---------------------------------------------------------------------------
# Adapter scripting
# ---------------------------------------------------------------------------
@given(parsers.re(r"^the adapter reports (?P<n>\d+) players?$"))
def _(w, n):
    w.adapter_env["FAKE_PLAYER_COUNT"] = n


@given('the adapter reports "unknown"')
def _(w):
    w.adapter_env["FAKE_PLAYER_COUNT"] = "unknown"


@given("the adapter player_count exits non-zero")
def _(w):
    w.adapter_env["FAKE_PLAYER_COUNT_RC"] = "1"


@given(parsers.parse('the adapter reports {n:d} players and health "{health}"'))
def _(w, n, health):
    w.adapter_env["FAKE_PLAYER_COUNT"] = str(n)
    w.adapter_env["FAKE_HEALTH"] = health


@given(parsers.parse('the adapter reports health "{health}" and player count "unknown"'))
def _(w, health):
    w.adapter_env["FAKE_HEALTH"] = health
    w.adapter_env["FAKE_PLAYER_COUNT"] = "unknown"


@given("the adapter reports is_ready success")
def _(w):
    w.adapter_env["FAKE_IS_READY"] = "0"


@given("the adapter reports is_ready not ready")
def _(w):
    w.adapter_env["FAKE_IS_READY"] = "1"


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------
@when(parsers.parse('a member runs "/bonfire {sub}"'))
def _(w, sub):
    w.run_command(sub)


@when("the agent runs its check")
def _(w):
    w.run_agent()


@when(parsers.re(r"^the agent runs its check at (?P<hh>\d\d):(?P<mm>\d\d)$"))
def _(w, hh, mm):
    w.clock.set(BASE_NOW.replace(hour=int(hh), minute=int(mm)))
    w.run_agent()


@when("the safety-net timer runs")
def _(w):
    w.run_watchdog()


@when('member A and member B run "/bonfire ignite" at the same time')
def _(w):
    # B's whole handler runs inside A's first conditional write, so A's ETag goes stale.
    w.table.before_write = lambda: w.run_command("ignite", member="B")
    w.run_command("ignite", member="A")


@given("another writer changes the state row between a handler's read and write")
def _(w):
    w.table.before_write = lambda: w.table.set(last_heartbeat=w.now())


@when("the handler writes with the ETag it read")
def _(w):
    w.run_command("ignite")


@given('a member has been shown message "confirm_extinguish"')
def _(w):
    w.run_command("extinguish")
    assert w.last_reply() == w.expect("confirm_extinguish", n=w.row().last_player_count)


@given(parsers.re(rf'^a member has been shown message "confirm_extinguish" (?P<dur>{DUR}) ago$'))
def _(w, dur):
    w.run_command("extinguish")
    w.clock.advance(seconds=duration(dur).total_seconds())


@when(parsers.re(r'^that member clicks "(?P<label>\w+)" within 2 minutes$'))
def _(w, label):
    w.click(label, "member")


@when(parsers.re(r'^that member clicks "(?P<label>\w+)"$'))
def _(w, label):
    w.click(label, "member")


@when(parsers.re(r'^a different member clicks "(?P<label>\w+)"$'))
def _(w, label):
    w.click(label, "different")


# ---------------------------------------------------------------------------
# Replies and messages
# ---------------------------------------------------------------------------
@then("the Function acknowledges with a deferred channel reply")
def _(w):
    assert w.last_http.body == {"type": 5}


@then("the Function acknowledges within 3 seconds with a deferred channel reply")
def _(w):
    assert w.last_http.body == {"type": 5}
    assert w.http_seconds < 3


@then(parsers.re(rf'^the reply is message "(?P<mid>\w+)"(?: with (?P<kv>{KV}))?$'))
def _(w, mid, kv):
    assert w.last_reply() == w.expect(mid, kv)


@then(parsers.parse('the reply is message "{mid}" mentioning the member'))
def _(w, mid):
    assert w.last_reply() == w.expect(mid, user=mention(MEMBERS["member"]))


@then(parsers.parse('the reply is a status message for state "{state}"'))
def _(w, state):
    prefix = {"lit": "The bonfire is lit", "out": "The bonfire is out", "igniting": "The bonfire is igniting",
              "extinguishing": "The bonfire is being extinguished"}[state]
    assert w.last_reply().startswith(prefix), w.last_reply()


@then(parsers.parse('the reply is message "confirm_extinguish" with n {n:d} and buttons "Extinguish" and "Cancel"'))
def _(w, n):
    edit = w.replies.edits[-1]
    assert edit.content == w.expect("confirm_extinguish", n=n)
    labels = [b["label"] for row in edit.components for b in row["components"]]
    assert labels == ["Extinguish", "Cancel"]


@then(parsers.re(rf'^the message is edited to "(?P<mid>\w+)"(?: with (?P<kv>{KV}))?$'))
def _(w, mid, kv):
    edit = w.replies.edits[-1]
    assert edit.content == w.expect(mid, kv)
    assert edit.components == []


@then(parsers.parse('the different member receives ephemeral message "{mid}"'))
def _(w, mid):
    follow = w.replies.follow_ups[-1]
    assert follow.token == w.tokens["different"] and follow.ephemeral
    assert follow.content == w.expect(mid)


@then('the member whose write succeeded receives message "igniting"')
def _(w):
    assert w.reply_for("B") == w.expect("igniting")


@then('the other member receives message "status_igniting"')
def _(w):
    assert w.reply_for("A") == w.expect("status_igniting", m=0)


@then(parsers.re(rf'^the webhook receives message "(?P<mid>\w+)"(?: with (?P<kv>{KV}))?$'))
def _(w, mid, kv):
    expected = w.expect(mid, kv)
    assert expected in w.webhook.posts, f"expected {expected!r} in {w.webhook.posts!r}"


@then("no message is posted")
def _(w):
    assert w.webhook.posts == []


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
@then(parsers.re(r'^a "(?P<type_>\w+)/(?P<action>\w+)" event is recorded(?P<rest>.*)$'))
def _(w, type_, action, rest):
    matches = w.events_of(type_, action)
    assert matches, f"no {type_}/{action}; have {[(e.type, e.action) for e in w.events.items]}"
    event = matches[-1]
    if "the member as actor" in rest:
        assert event.actor == MEMBERS["member"]
    if "ok true" in rest:
        assert event.ok is True
    if "ok false" in rest:
        assert event.ok is False
    m = re.search(r"player_count (\d+)", rest)
    if m:
        assert event.player_count == int(m.group(1))
    m = re.search(r"duration_ms of about (\d+)", rest)
    if m:
        assert event.duration_ms is not None and abs(event.duration_ms - int(m.group(1))) <= 5000


# ---------------------------------------------------------------------------
# Compute
# ---------------------------------------------------------------------------
@then("a VM start is requested exactly once")
def _(w):
    assert w.compute_fn.starts == 1


@then("no VM start is requested")
def _(w):
    assert w.compute_fn.starts == 0


@then("a VM deallocate is requested by the agent exactly once")
def _(w):
    assert w.compute_agent.deallocates == 1


@then("a VM deallocate is requested by the Function exactly once")
def _(w):
    assert w.compute_fn.deallocates == 1


@then("no VM deallocate is requested")
def _(w):
    assert w.compute_fn.deallocates == 0 and w.compute_agent.deallocates == 0


@then("no VM deallocate is requested by the Function")
def _(w):
    assert w.compute_fn.deallocates == 0


# ---------------------------------------------------------------------------
# Adapter invocations
# ---------------------------------------------------------------------------
@then(parsers.re(r'^the adapter "(?P<sub>\w+)" subcommand is invoked before (?:any|the) deallocate$'))
def _(w, sub):
    calls = w.calls()
    assert sub in calls and "deallocate" in calls, calls
    assert calls.index(sub) < calls.index("deallocate"), calls


@then(parsers.parse('the adapter "{sub}" subcommand is not invoked'))
def _(w, sub):
    assert sub not in w.calls()


# ---------------------------------------------------------------------------
# State row assertions
# ---------------------------------------------------------------------------
def _minutes_equal(a: datetime | None, b: datetime | None) -> bool:
    return a is not None and b is not None and abs((a - b).total_seconds()) < 1


@then("the state row is unchanged")
def _(w):
    assert w.row() == w.snapshot


@then(parsers.re(r'^the state row has vm_state "(?P<state>\w+)"$'))
def _(w, state):
    assert w.row().vm_state == state


@then(parsers.re(r'^the state row still has vm_state "(?P<state>\w+)"$'))
def _(w, state):
    assert w.row().vm_state == state


@then(parsers.re(r'^the state row has vm_state "(?P<state>\w+)" and lock_until null$'))
def _(w, state):
    row = w.row()
    assert row.vm_state == state and row.lock_until is None


@then(parsers.re(r'^the state row has vm_state "(?P<state>\w+)" and session_ended_at now$'))
def _(w, state):
    row = w.row()
    assert row.vm_state == state and _minutes_equal(row.session_ended_at, w.now())


@then('the state row has vm_state "extinguishing", session_ended_at now, and lock_until 5 minutes ahead')
def _(w):
    row = w.row()
    assert row.vm_state == "extinguishing"
    assert _minutes_equal(row.session_ended_at, w.now())
    assert _minutes_equal(row.lock_until, w.now() + timedelta(minutes=5))


@then('the state row has vm_state "igniting", a new session_id, session_started_at now, and lock_until 5 minutes ahead')
def _(w):
    row = w.row()
    assert row.vm_state == "igniting"
    assert row.session_id and row.session_id != w.snapshot.session_id
    assert _minutes_equal(row.session_started_at, w.now())
    assert _minutes_equal(row.lock_until, w.now() + timedelta(minutes=5))


@then(parsers.parse('the state row has vm_state "lit", lock_until null, and last_health "{health}"'))
def _(w, health):
    row = w.row()
    assert row.vm_state == "lit" and row.lock_until is None and row.last_health == health


@then('the state row has vm_state "out", session fields null, lock_until null')
def _(w):
    row = w.row()
    assert row.vm_state == "out" and row.lock_until is None
    assert row.session_id is None and row.session_started_at is None and row.session_ended_at is None


@then('the state row passes through vm_state "out" and ends in "igniting"')
def _(w):
    assert "out" in w.table.history and w.table.history[-1] == "igniting"
    assert w.table.history.index("out") < len(w.table.history) - 1


@then(parsers.parse("hours_this_month is about {hours:g}"))
def _(w, hours):
    assert abs(w.row().hours_this_month - hours) < 0.01


@then("idle_since is null")
def _(w):
    assert w.row().idle_since is None


@then(parsers.re(r"^idle_since is (?P<hh>\d\d):(?P<mm>\d\d)$"))
def _(w, hh, mm):
    assert w.row().idle_since == BASE_NOW.replace(hour=int(hh), minute=int(mm))


@then(parsers.re(rf"^idle_since is still (?P<when>{REL})$"))
def _(w, when):
    assert _minutes_equal(w.row().idle_since, rel(when, w.now()))


@then('idle_since is null and warnings_posted is ""')
def _(w):
    row = w.row()
    assert row.idle_since is None and row.warnings_posted == ""


@then(parsers.re(r'^warnings_posted is "(?P<posted>[^"]*)"$'))
def _(w, posted):
    assert w.row().warnings_posted == posted


@then("unknown_alerted is true")
def _(w):
    assert w.row().unknown_alerted is True


@then("unknown_since is null and unknown_alerted is false")
def _(w):
    row = w.row()
    assert row.unknown_since is None and row.unknown_alerted is False


@then("ceiling_warned is true")
def _(w):
    assert w.row().ceiling_warned is True


@then(parsers.parse("last_player_count is {n:d}"))
def _(w, n):
    assert w.row().last_player_count == n


@then(parsers.parse('last_health is "{health}"'))
def _(w, health):
    assert w.row().last_health == health


@then(parsers.re(r'^last_heartbeat is (?P<hh>\d\d):(?P<mm>\d\d), last_player_count is (?P<n>\d+), and last_health is "(?P<health>\w+)"$'))
def _(w, hh, mm, n, health):
    row = w.row()
    assert row.last_heartbeat == BASE_NOW.replace(hour=int(hh), minute=int(mm))
    assert row.last_player_count == int(n) and row.last_health == health


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------
@then("exactly one conditional write to the state row succeeds")
def _(w):
    assert sum(1 for _, ok in w.table.writes if ok) == 1, w.table.writes


@then("the write fails with a precondition error")
def _(w):
    assert any(not ok for _, ok in w.table.writes), w.table.writes


@then("the handler re-reads the row before deciding what to do")
def _(w):
    assert w.table.reads >= 2
    assert w.table.writes[-1][1] is True
