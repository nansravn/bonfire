"""Message catalog, signature verification and event documents."""
import json
import re
from datetime import datetime, timezone

import pytest

from bonfire.core.discord import MESSAGES, extinguish_buttons, mention, render, verify_signature
from bonfire.core.events import Event
from fakes import Signer

pytestmark = pytest.mark.unit
SAMPLE = {"m": 1, "n": 3, "h": 1, "mm": "05", "r": 32, "w": 15, "user": "<@1>", "address": "203.0.113.10:2456",
          "ready_timeout_minutes": 10, "idle_timeout_minutes": 45, "UNKNOWN_ALERT_MINUTES": 60,
          "max_session_hours": 12, "heartbeat_stale_minutes": 20, "vm": "12.34", "fixed": "18.00"}


def test_every_catalog_entry_renders_without_leftover_braces():
    for message_id in MESSAGES:
        text = render(message_id, **SAMPLE)
        assert not re.search(r"[{}]", text), (message_id, text)


def test_copy_matches_the_contract():
    assert render("igniting") == "Lighting the bonfire, ~2 min."
    assert render("status_lit", n=3, h=1, mm="20") == "The bonfire is lit: 3 players online, lit for 1h 20m."
    assert render("extinguished_manual", user=mention("42")) == "Bonfire extinguished by <@42>."


def test_signature_round_trip():
    signer = Signer()
    body = json.dumps({"type": 1}).encode()
    headers = signer.headers("1700000000", body)
    assert verify_signature(signer.public_key_hex, headers["X-Signature-Ed25519"], "1700000000", body)
    assert not verify_signature(signer.public_key_hex, headers["X-Signature-Ed25519"], "1700000001", body)
    assert not verify_signature(signer.public_key_hex, "00" * 64, "1700000000", body)
    assert not verify_signature(signer.public_key_hex, "not-hex", "1700000000", body)


def test_extinguish_buttons_carry_owner_and_timestamp():
    rows = extinguish_buttons("42", 1700000000)
    buttons = rows[0]["components"]
    assert [b["label"] for b in buttons] == ["Extinguish", "Cancel"]
    assert buttons[0]["custom_id"] == "extinguish:confirm:42:1700000000"
    assert buttons[1]["custom_id"] == "extinguish:cancel:42:1700000000"
    assert buttons[0]["style"] == 4 and buttons[1]["style"] == 2


def test_event_document_shape():
    ts = datetime(2026, 9, 12, 23, 4, 11, tzinfo=timezone.utc)
    doc = Event(type="command", action="ignite", actor="1", ts=ts, session_id="s", duration_ms=1830,
                detail="x" * 600).to_document()
    assert doc["month"] == "2026-09" and doc["ts"] == "2026-09-12T23:04:11Z"
    assert doc["ok"] is True and doc["player_count"] is None
    assert len(doc["detail"]) == 500 and len(doc["id"]) == 36


def test_event_rejects_unknown_action():
    with pytest.raises(ValueError):
        Event(type="vm", action="exploded", actor="agent", ts=datetime.now(timezone.utc))
