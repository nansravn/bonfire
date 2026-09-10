"""Configuration from the environment, validated per docs/contracts/configuration.md."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

WATCHDOG_INTERVAL_MINUTES = 15
UNKNOWN_ALERT_MINUTES = 60
LOCK_TTL_MINUTES = 5


class ConfigError(ValueError):
    """Raised with the text of the rule that failed."""


@dataclass(frozen=True)
class Config:
    game: str = "valheim"
    idle_timeout_minutes: int = 45
    idle_warning_minutes: tuple[int, ...] = (15, 5)
    idle_check_interval: int = 1
    max_session_hours: int = 12
    heartbeat_stale_minutes: int = 20
    vm_hourly_usd: float = 0.30
    fixed_monthly_usd: float = 18.0
    public_address: str = ""
    vm_resource_id: str = ""
    state_table_endpoint: str = ""
    events_endpoint: str = ""

    def validate(self) -> None:
        if self.idle_check_interval < 1:
            raise ConfigError("idle_check_interval must be at least 1")
        if not self.idle_timeout_minutes > self.idle_check_interval:
            raise ConfigError("idle_timeout_minutes must be greater than idle_check_interval")
        w = self.idle_warning_minutes
        if any(a <= b for a, b in zip(w, w[1:])):
            raise ConfigError("idle_warning_minutes must be strictly descending")
        for x in w:
            if not (self.idle_check_interval < x < self.idle_timeout_minutes):
                raise ConfigError(
                    f"idle_warning_minutes entry {x} must be below idle_timeout_minutes and above idle_check_interval"
                )
        if self.max_session_hours < 2:
            raise ConfigError("max_session_hours must be at least 2")
        if self.heartbeat_stale_minutes < 3 * self.idle_check_interval or self.heartbeat_stale_minutes <= WATCHDOG_INTERVAL_MINUTES:
            raise ConfigError(
                "heartbeat_stale_minutes must be at least 3 x idle_check_interval and greater than the 15-minute watchdog interval"
            )
        if self.vm_hourly_usd <= 0:
            raise ConfigError("vm_hourly_usd must be greater than 0")
        if self.fixed_monthly_usd < 0:
            raise ConfigError("fixed_monthly_usd must be at least 0")


def _list(text: str) -> tuple[int, ...]:
    return tuple(int(x) for x in text.split(",") if x.strip())


def load_config(env: Mapping[str, str]) -> Config:
    d = Config()
    try:
        cfg = Config(
            game=env.get("BONFIRE_GAME", d.game),
            idle_timeout_minutes=int(env.get("BONFIRE_IDLE_TIMEOUT_MINUTES", d.idle_timeout_minutes)),
            idle_warning_minutes=_list(env["BONFIRE_IDLE_WARNING_MINUTES"]) if "BONFIRE_IDLE_WARNING_MINUTES" in env else d.idle_warning_minutes,
            idle_check_interval=int(env.get("BONFIRE_IDLE_CHECK_INTERVAL", d.idle_check_interval)),
            max_session_hours=int(env.get("BONFIRE_MAX_SESSION_HOURS", d.max_session_hours)),
            heartbeat_stale_minutes=int(env.get("BONFIRE_HEARTBEAT_STALE_MINUTES", d.heartbeat_stale_minutes)),
            vm_hourly_usd=float(env.get("BONFIRE_VM_HOURLY_USD", d.vm_hourly_usd)),
            fixed_monthly_usd=float(env.get("BONFIRE_FIXED_MONTHLY_USD", d.fixed_monthly_usd)),
            public_address=env.get("BONFIRE_PUBLIC_ADDRESS", ""),
            vm_resource_id=env.get("BONFIRE_VM_RESOURCE_ID", ""),
            state_table_endpoint=env.get("BONFIRE_STATE_TABLE_ENDPOINT", ""),
            events_endpoint=env.get("BONFIRE_EVENTS_ENDPOINT", ""),
        )
    except ValueError as exc:
        raise ConfigError(f"malformed value: {exc}") from exc
    cfg.validate()
    return cfg
