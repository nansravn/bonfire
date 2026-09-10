"""The Interactions Endpoint: verify, answer PING, enqueue and defer (spec 6.1, ADR 0008)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from bonfire.core.clock import iso
from bonfire.core.discord import verify_signature

PING, COMMAND, BUTTON = 1, 2, 3
PONG, DEFERRED_CHANNEL_MESSAGE, DEFERRED_UPDATE_MESSAGE = 1, 5, 6


@dataclass
class HttpResult:
    status: int
    body: dict | None
    queue_message: str | None = None


def handle_http(headers: Mapping[str, str], body: bytes, public_key_hex: str, now: datetime) -> HttpResult:
    lower = {k.lower(): v for k, v in headers.items()}
    signature = lower.get("x-signature-ed25519")
    timestamp = lower.get("x-signature-timestamp")
    if not signature or not timestamp or not verify_signature(public_key_hex, signature, timestamp, body):
        return HttpResult(401, None)
    try:
        interaction = json.loads(body)
    except ValueError:
        return HttpResult(400, None)
    kind = interaction.get("type")
    if kind == PING:
        return HttpResult(200, {"type": PONG})
    if kind in (COMMAND, BUTTON):
        message = json.dumps({"received_at": iso(now), "interaction": interaction})
        ack = DEFERRED_CHANNEL_MESSAGE if kind == COMMAND else DEFERRED_UPDATE_MESSAGE
        return HttpResult(200, {"type": ack}, message)
    return HttpResult(400, None)
