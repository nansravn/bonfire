"""Binds tests/features/check.feature (unit level)."""
from pytest_bdd import scenarios

from unit_steps import *  # noqa: F401,F403

scenarios("check.feature")
