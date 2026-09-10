"""Spec 6.1: the HTTP trigger verifies, answers PING, enqueues and defers."""
import json
from datetime import datetime, timezone

import pytest

from bonfire.function.interactions import handle_http
from fakes import Signer

pytestmark = pytest.mark.unit
NOW = datetime(2026, 9, 12, 20, 0, tzinfo=timezone.utc)


@pytest.fixture
def signer():
    return Signer()


def post(signer, payload, tamper=False, drop_headers=False):
    body = json.dumps(payload).encode()
    headers = {} if drop_headers else signer.headers("1700000000", body)
    if tamper:
        body = body + b" "
    return handle_http(headers, body, signer.public_key_hex, NOW)


def test_missing_signature_is_401(signer):
    assert post(signer, {"type": 1}, drop_headers=True).status == 401


def test_bad_signature_is_401(signer):
    result = post(signer, {"type": 1}, tamper=True)
    assert result.status == 401 and result.queue_message is None


def test_ping_gets_pong(signer):
    result = post(signer, {"type": 1})
    assert result.status == 200 and result.body == {"type": 1} and result.queue_message is None


def test_command_is_deferred_and_enqueued(signer):
    interaction = {"type": 2, "token": "tok", "data": {"name": "bonfire", "options": [{"type": 1, "name": "ignite"}]}}
    result = post(signer, interaction)
    assert result.status == 200 and result.body == {"type": 5}
    message = json.loads(result.queue_message)
    assert message == {"received_at": "2026-09-12T20:00:00Z", "interaction": interaction}


def test_button_is_deferred_update(signer):
    result = post(signer, {"type": 3, "token": "tok", "data": {"custom_id": "extinguish:cancel:1:2"}})
    assert result.body == {"type": 6} and result.queue_message is not None


def test_unknown_type_is_400(signer):
    assert post(signer, {"type": 9}).status == 400


def test_headers_are_case_insensitive(signer):
    body = json.dumps({"type": 1}).encode()
    headers = {k.lower(): v for k, v in signer.headers("1700000000", body).items()}
    assert handle_http(headers, body, signer.public_key_hex, NOW).status == 200
