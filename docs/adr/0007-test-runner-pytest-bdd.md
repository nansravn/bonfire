# 0007. Test runner: pytest-bdd

**Status:** Accepted
**Date:** 2026-09-09

## Context

The behaviour of Bonfire is specified as Gherkin feature files under `tests/features/` ([testing.md](../testing.md)). Phase 0 needs to execute the Valheim adapter's contract scenarios on a Docker host and in CI, which forces the choice of a runner one phase earlier than the documentation map planned.

## Decision

pytest with the pytest-bdd plugin. Step definitions are Python under `tests/steps/`; feature tags become pytest markers, so a level is selected with `pytest -m contract`.

## Alternatives considered

### behave

Rejected. A separate runner without pytest's fixtures, markers and plugin ecosystem.

### cucumber-js

Rejected. A second language in the repository for tests alone.

### A bash conformance script

Rejected. It would duplicate the feature file and be thrown away when a real runner arrived.

## Consequences

- Tests are Python 3.12 or newer; the agent, when written, will be Python too, sharing the A2S library and the test tooling.
- `pytest.ini` registers the three level markers and points pytest-bdd at `tests/features/`.
- Only feature files bound by a step module are collected; unbound files are documentation until their phase implements them.
