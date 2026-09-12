"""Discord: message catalog, signature check, webhook and reply clients (docs/contracts/discord.md)."""
from __future__ import annotations

from typing import Any, Protocol

MESSAGES: dict[str, str] = {
    "igniting": "Lighting the bonfire, ~2 min.",
    "status_out": "The bonfire is out. /bonfire ignite to light it.",
    "status_igniting": "The bonfire is igniting ({m} min so far, usually ready in ~2 min).",
    "status_lit": "The bonfire is lit: {n} players online, lit for {h}h {mm}m.",
    "status_lit_idle": "The bonfire is lit: 0 players online, lit for {h}h {mm}m. Burns out in {r} min unless someone joins.",
    "status_lit_unknown": "The bonfire is lit, but the player count is unknown (auto-extinguish paused). Lit for {h}h {mm}m.",
    "status_lit_crashed": "The bonfire is lit but the game is down. Try /bonfire restart.",
    "status_extinguishing": "The bonfire is being extinguished.",
    "ready": "Bonfire lit — server ready. Connect to {address}.",
    "ignite_failed": "Failed to ignite: the game did not become ready in {ready_timeout_minutes} min. The VM stays up for diagnosis until the session ceiling.",
    "warning": "The bonfire will burn out in {w} min with nobody around.",
    "idle_cancelled": "Someone joined — auto-extinguish cancelled.",
    "idle_shutdown": "The bonfire burned out after {idle_timeout_minutes} min with no one around. /bonfire ignite to bring it back.",
    "unknown_alert": "Player count has been unknown for {UNKNOWN_ALERT_MINUTES} min. Auto-extinguish is paused; check the server.",
    "extinguished_manual": "Bonfire extinguished by {user}.",
    "confirm_extinguish": "{n} players are online. Extinguish anyway?",
    "extinguished_manual_with_players": "Bonfire extinguished by {user} with {n} players online.",
    "confirm_cancelled": "Kept lit.",
    "confirm_not_yours": "Only the person who ran /bonfire extinguish can confirm.",
    "confirm_expired": "This prompt expired. Run /bonfire extinguish again.",
    "restarting": "Restarting the game; the bonfire stays lit.",
    "crash": "The game crashed; Docker is restarting it.",
    "crash_gave_up": "The game crashed repeatedly and stays down. Fix it and use /bonfire restart.",
    "watchdog_ceiling_warning": "The bonfire has been lit for {h} h; the safety net puts it out at {max_session_hours} h.",
    "watchdog_ceiling": "Safety net: the bonfire has been lit for {max_session_hours} h and was extinguished. /bonfire ignite to bring it back.",
    "watchdog_heartbeat": "Safety net: no heartbeat from the server for {heartbeat_stale_minutes} min; the bonfire was extinguished.",
    "watchdog_boot_failed": "Safety net: the server never reported in after {heartbeat_stale_minutes} min; the bonfire was extinguished. Check the VM boot logs.",
    "cost": "Lit {h} h this month: about US${vm} for the VM plus US${fixed} fixed (disks, IP, storage).",
}

DISCORD_API = "https://discord.com/api/v10"


def render(message_id: str, **placeholders: Any) -> str:
    return MESSAGES[message_id].format(**placeholders)


def describe_error(exc: BaseException) -> str:
    """Class name plus HTTP status when present; never the message, which may carry a URL with a token."""
    status = getattr(getattr(exc, "response", None), "status_code", None)
    return f"{type(exc).__name__}{f' {status}' if status is not None else ''}"


def mention(user_id: str) -> str:
    return f"<@{user_id}>"


def verify_signature(public_key_hex: str, signature_hex: str, timestamp: str, body: bytes) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        key.verify(bytes.fromhex(signature_hex), timestamp.encode() + body)
        return True
    except (ValueError, InvalidSignature):
        return False


def extinguish_buttons(user_id: str, unix_ts: int) -> list[dict[str, Any]]:
    return [{
        "type": 1,
        "components": [
            {"type": 2, "style": 4, "label": "Extinguish", "custom_id": f"extinguish:confirm:{user_id}:{unix_ts}"},
            {"type": 2, "style": 2, "label": "Cancel", "custom_id": f"extinguish:cancel:{user_id}:{unix_ts}"},
        ],
    }]


class Webhook(Protocol):
    def post(self, content: str) -> None: ...


class Replies(Protocol):
    def edit_original(self, token: str, content: str, components: list | None = None) -> None: ...
    def follow_up(self, token: str, content: str, ephemeral: bool = False) -> None: ...


class HttpWebhook:
    def __init__(self, url: str) -> None:
        self._url = url

    def post(self, content: str) -> None:
        import requests

        requests.post(self._url, json={"content": content}, timeout=10).raise_for_status()


class HttpReplies:
    def __init__(self, application_id: str) -> None:
        self._application_id = application_id

    def _base(self, token: str) -> str:
        return f"{DISCORD_API}/webhooks/{self._application_id}/{token}"

    def edit_original(self, token: str, content: str, components: list | None = None) -> None:
        import requests

        payload: dict[str, Any] = {"content": content, "components": components or []}
        requests.patch(f"{self._base(token)}/messages/@original", json=payload, timeout=10).raise_for_status()

    def follow_up(self, token: str, content: str, ephemeral: bool = False) -> None:
        import requests

        payload: dict[str, Any] = {"content": content, "flags": 64 if ephemeral else 0}
        requests.post(self._base(token), json=payload, timeout=10).raise_for_status()
