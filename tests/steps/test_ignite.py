"""Binds tests/features/ignite.feature (unit level)."""
from pytest_bdd import scenarios

from unit_steps import *  # noqa: F401,F403

scenarios("ignite.feature")
