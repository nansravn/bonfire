"""Configuration parsing and validation (docs/contracts/configuration.md)."""
import pytest

from bonfire.core.config import Config, ConfigError, load_config

pytestmark = pytest.mark.unit


def test_defaults_are_valid():
    cfg = load_config({})
    assert cfg.idle_timeout_minutes == 45
    assert cfg.idle_warning_minutes == (15, 5)
    assert cfg.heartbeat_stale_minutes == 20


def test_reads_every_variable():
    cfg = load_config({
        "BONFIRE_GAME": "valheim",
        "BONFIRE_IDLE_TIMEOUT_MINUTES": "30",
        "BONFIRE_IDLE_WARNING_MINUTES": "10,2",
        "BONFIRE_IDLE_CHECK_INTERVAL": "1",
        "BONFIRE_MAX_SESSION_HOURS": "8",
        "BONFIRE_HEARTBEAT_STALE_MINUTES": "16",
        "BONFIRE_VM_HOURLY_USD": "0.30",
        "BONFIRE_FIXED_MONTHLY_USD": "18",
        "BONFIRE_PUBLIC_ADDRESS": "203.0.113.10:2456",
        "BONFIRE_VM_RESOURCE_ID": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
        "BONFIRE_STATE_TABLE_ENDPOINT": "https://st.table.core.windows.net",
        "BONFIRE_EVENTS_ENDPOINT": "https://c.documents.azure.com:443/",
    })
    assert cfg.idle_warning_minutes == (10, 2)
    assert cfg.max_session_hours == 8
    assert cfg.vm_hourly_usd == 0.30
    assert cfg.public_address == "203.0.113.10:2456"


@pytest.mark.parametrize("env,rule", [
    ({"BONFIRE_IDLE_WARNING_MINUTES": "5,15"}, "descending"),
    ({"BONFIRE_IDLE_WARNING_MINUTES": "45,5"}, "idle_timeout_minutes"),
    ({"BONFIRE_IDLE_TIMEOUT_MINUTES": "1"}, "idle_check_interval"),
    ({"BONFIRE_HEARTBEAT_STALE_MINUTES": "10"}, "heartbeat_stale_minutes"),
    ({"BONFIRE_MAX_SESSION_HOURS": "1"}, "max_session_hours"),
    ({"BONFIRE_VM_HOURLY_USD": "0"}, "vm_hourly_usd"),
])
def test_rules_are_enforced(env, rule):
    with pytest.raises(ConfigError, match=rule):
        load_config(env)


def test_config_is_frozen():
    with pytest.raises(Exception):
        Config().idle_timeout_minutes = 1  # type: ignore[misc]
