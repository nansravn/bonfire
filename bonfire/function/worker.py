"""Queue worker: the command and button handlers that run after the HTTP ack (spec 6.2)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from bonfire.core.clock import Clock, parse_iso
from bonfire.core.compute import Compute
from bonfire.core.config import Config
from bonfire.core.discord import Replies, Webhook, describe_error, extinguish_buttons, mention, render
from bonfire.core.events import Event, EventSink
from bonfire.core.state import (
    PreconditionFailed,
    StateRow,
    StateTable,
    begin_extinguish,
    begin_ignite,
    finish_session,
)
from bonfire.function.reconcile import needs_power_state, reconcile
from bonfire.function.status import status_reply

log = logging.getLogger("bonfire.worker")
MAX_ATTEMPTS = 3
ALIASES = {"start": "ignite", "stop": "extinguish"}


@dataclass
class Clients:
    config: Config
    clock: Clock
    state: StateTable
    events: EventSink
    compute: Compute
    webhook: Webhook
    replies: Replies


@dataclass
class Ctx:
    clients: Clients
    token: str
    user_id: str
    received_at: datetime
    reply_failure: str = ""


def handle_interaction(message: dict, clients: Clients) -> None:
    interaction = message["interaction"]
    ctx = Ctx(clients, interaction["token"], _user_id(interaction), parse_iso(message["received_at"]))
    if interaction["type"] == 2:
        name = interaction["data"]["options"][0]["name"]
        handler = COMMANDS.get(ALIASES.get(name, name))
        if handler is None:
            log.warning("unknown subcommand %s", name)
            return
        handler(ctx)
    elif interaction["type"] == 3:
        custom_id = interaction["data"]["custom_id"]
        handler = BUTTONS.get(custom_id.split(":", 1)[0])
        if handler is None:
            log.warning("unknown button %s", custom_id)
            return
        handler(ctx, custom_id.split(":"))


def _user_id(interaction: dict) -> str:
    member = interaction.get("member") or {}
    user = member.get("user") or interaction.get("user") or {}
    return str(user.get("id", "unknown"))


def _now(ctx: Ctx) -> datetime:
    return ctx.clients.clock.now()


def _read_reconciled(ctx: Ctx) -> StateRow | None:
    """Read the row and apply rule 3 when it applies. None means the row moved under us: call again."""
    c = ctx.clients
    now = _now(ctx)
    row = c.state.read()
    if not needs_power_state(row, now):
        return row
    result = reconcile(row, c.compute.power_state(), now, c.config)
    if result.deallocate:
        c.compute.deallocate()
    for event in result.events:
        c.events.record(event)
    if result.row == row:
        return row
    try:
        return c.state.write(result.row)
    except PreconditionFailed:
        return None


def _reply(ctx: Ctx, content: str, components: list | None = None) -> None:
    try:
        ctx.clients.replies.edit_original(ctx.token, content, components)
    except Exception as exc:  # the state change stands; the event carries the failure (decision P12)
        log.warning("reply edit failed: %s", describe_error(exc))
        ctx.reply_failure = f"; reply failed: {describe_error(exc)}"


def _record(ctx: Ctx, action: str, row: StateRow, ok: bool = True, detail: str = "",
            player_count: int | None = None) -> None:
    now = _now(ctx)
    ctx.clients.events.record(Event(
        type="command", action=action, actor=ctx.user_id, ts=now, session_id=row.session_id,
        player_count=player_count, duration_ms=int((now - ctx.received_at).total_seconds() * 1000),
        ok=ok, detail=(detail + ctx.reply_failure)[:500],
    ))


def _status(ctx: Ctx, action: str, row: StateRow) -> None:
    _reply(ctx, status_reply(row, _now(ctx), ctx.clients.config))
    _record(ctx, action, row, detail=f"already {row.vm_state}")


def _conflict(ctx: Ctx, action: str) -> None:
    row = ctx.clients.state.read()
    _reply(ctx, status_reply(row, _now(ctx), ctx.clients.config))
    _record(ctx, action, row, ok=False, detail="etag conflict")


def _check(ctx: Ctx) -> None:
    for _ in range(MAX_ATTEMPTS):
        row = _read_reconciled(ctx)
        if row is None:
            continue
        _reply(ctx, status_reply(row, _now(ctx), ctx.clients.config))
        _record(ctx, "check", row)
        return
    _conflict(ctx, "check")


def _cost(ctx: Ctx) -> None:
    c = ctx.clients
    row = c.state.read()
    hours = row.hours_this_month if row.hours_month == _now(ctx).strftime("%Y-%m") else 0.0
    _reply(ctx, render("cost", h=int(hours), vm=f"{hours * c.config.vm_hourly_usd:.2f}",
                       fixed=f"{c.config.fixed_monthly_usd:.2f}"))
    _record(ctx, "cost", row, detail=f"{hours:.2f} h")


def _ignite(ctx: Ctx) -> None:
    c = ctx.clients
    for _ in range(MAX_ATTEMPTS):
        row = _read_reconciled(ctx)
        if row is None:
            continue
        if row.vm_state != "out":
            _status(ctx, "ignite", row)
            return
        new = begin_ignite(row.copy(), _now(ctx), str(uuid.uuid4()))
        try:
            new = c.state.write(new)
        except PreconditionFailed:
            continue
        try:
            c.compute.start()
        except Exception as exc:
            log.error("vm start failed: %s", describe_error(exc))
            reverted = new.copy()
            finish_session(reverted, _now(ctx))  # back to out; no hours (session_ended_at is None)
            try:
                c.state.write(reverted)
            except PreconditionFailed:
                log.warning("row moved while reverting a failed ignite; leaving it to reconciliation")
            _reply(ctx, render("status_out"))
            _record(ctx, "ignite", reverted, ok=False, detail=f"vm start failed: {describe_error(exc)}")
            return
        _reply(ctx, render("igniting"))
        _record(ctx, "ignite", new, detail="vm start accepted")
        return
    _conflict(ctx, "ignite")


def _extinguish(ctx: Ctx) -> None:
    c = ctx.clients
    for _ in range(MAX_ATTEMPTS):
        row = _read_reconciled(ctx)
        if row is None:
            continue
        if row.vm_state != "lit":
            _status(ctx, "extinguish", row)
            return
        if row.last_player_count > 0:
            buttons = extinguish_buttons(ctx.user_id, int(_now(ctx).timestamp()))
            _reply(ctx, render("confirm_extinguish", n=row.last_player_count), buttons)
            return
        new = begin_extinguish(row.copy(), _now(ctx))
        try:
            new = c.state.write(new)
        except PreconditionFailed:
            continue
        _reply(ctx, render("extinguished_manual", user=mention(ctx.user_id)))
        _record(ctx, "extinguish", new, player_count=None if row.last_player_count < 0 else row.last_player_count)
        return
    _conflict(ctx, "extinguish")


CONFIRM_WINDOW_SECONDS = 120


def _extinguish_button(ctx: Ctx, parts: list[str]) -> None:
    """custom_id = extinguish:<confirm|cancel>:<owner user id>:<unix ts> (docs/contracts/discord.md)."""
    c = ctx.clients
    verb, owner, issued = parts[1], parts[2], int(parts[3])
    if ctx.user_id != owner:
        try:
            c.replies.follow_up(ctx.token, render("confirm_not_yours"), ephemeral=True)
        except Exception as exc:
            log.warning("ephemeral follow-up failed: %s", describe_error(exc))
        return
    if _now(ctx).timestamp() - issued > CONFIRM_WINDOW_SECONDS:
        _reply(ctx, render("confirm_expired"), [])
        return
    if verb == "cancel":
        _reply(ctx, render("confirm_cancelled"), [])
        return
    for _ in range(MAX_ATTEMPTS):
        row = _read_reconciled(ctx)
        if row is None:
            continue
        if row.vm_state != "lit":
            _reply(ctx, status_reply(row, _now(ctx), c.config), [])
            return
        n = max(row.last_player_count, 0)
        new = begin_extinguish(row.copy(), _now(ctx))
        try:
            new = c.state.write(new)
        except PreconditionFailed:
            continue
        _reply(ctx, render("extinguished_manual_with_players", user=mention(ctx.user_id), n=n), [])
        _record(ctx, "extinguish", new, player_count=n)
        return
    _conflict(ctx, "extinguish")


COMMANDS = {"ignite": _ignite, "extinguish": _extinguish, "check": _check, "cost": _cost}
BUTTONS = {"extinguish": _extinguish_button}
