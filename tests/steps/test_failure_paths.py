"""Final-review fixes: redacted Discord error details (finding 1) and a reverted failed ignite (finding 2)."""
from types import SimpleNamespace

import pytest
import requests

from bonfire.core.discord import describe_error, render
from unit_steps import MEMBERS, World

pytestmark = pytest.mark.unit


@pytest.fixture
def w(tmp_path) -> World:
    return World(tmp_path)


def test_describe_error_reports_class_and_status_never_message():
    exc = RuntimeError("boom")
    exc.response = SimpleNamespace(status_code=429)
    assert describe_error(exc) == "RuntimeError 429"


def test_failed_reply_edit_detail_omits_the_secret_token(w: World):
    """A reply-edit failure's HTTPError text carries the interaction token; only the class/status may reach detail."""
    secret_url = "https://discord.com/api/v10/webhooks/app/SECRET-TOKEN/messages/@original"

    def raise_http_error(token, content, components=None):
        raise requests.HTTPError(f"401 Client Error for url: {secret_url}")

    w.replies.edit_original = raise_http_error
    w.set_row(vm_state="out")

    w.run_command("check")

    events = w.events_of("command", "check")
    assert events, "expected a command/check event to be recorded"
    detail = events[-1].detail
    assert "HTTPError" in detail
    assert "SECRET-TOKEN" not in detail
    assert secret_url not in detail


def test_failed_vm_start_reverts_the_row_to_out(w: World):
    """A compute.start() failure must not strand the row in igniting for 5 minutes (finding 2)."""

    def raise_start_error():
        raise RuntimeError("boom")

    w.compute_fn.start = raise_start_error
    w.set_row(vm_state="out")

    w.run_command("ignite")

    row = w.row()
    assert row.vm_state == "out"
    assert row.session_id is None
    assert w.last_reply() == render("status_out")

    events = w.events_of("command", "ignite")
    assert events, "expected a command/ignite event to be recorded"
    last = events[-1]
    assert last.ok is False
    assert "vm start failed" in last.detail

    assert w.table.history[-3:] == ["out", "igniting", "out"]
