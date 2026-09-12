"""The agent process refuses an invalid configuration before touching anything (spec 7)."""
import pytest

from bonfire.agent.__main__ import main

pytestmark = pytest.mark.unit


def test_invalid_configuration_exits_2(capsys):
    rc = main({"BONFIRE_IDLE_WARNING_MINUTES": "5,15", "BONFIRE_ADAPTER_DIR": "/nonexistent"})
    assert rc == 2
    assert "strictly descending" in capsys.readouterr().err


def test_missing_adapter_dir_exits_2(capsys):
    rc = main({})
    assert rc == 2
    assert "BONFIRE_ADAPTER_DIR" in capsys.readouterr().err
