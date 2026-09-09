# Testing

Three levels. Each feature file declares its level with a tag on every scenario, so one runner can select a level with a tag expression.

| Level | Tag | Runs where | Exercises | Needs Azure |
|---|---|---|---|---|
| Unit | `@unit` | Local, no Docker | Agent idle and heartbeat logic against a fake adapter and an in-memory state row; Function handlers against signed fake Discord payloads and a fake Azure client | No |
| Adapter contract | `@contract` | Local Docker host | `adapter.sh` conformance with the real game image | No |
| End-to-end | `@e2e` | The pilot VM and Function | Ignite to ready, idle to deallocate, safety net | Yes |

## Feature files

| File | Level(s) | What it pins |
|---|---|---|
| `tests/features/ignite.feature` | unit | Ignite from every state; readiness; ignite failure |
| `tests/features/extinguish.feature` | unit | Extinguish with and without players; confirmation; deallocation completion |
| `tests/features/check.feature` | unit | Status reply in every state |
| `tests/features/idle-shutdown.feature` | unit | Warnings, cancellation, unknown rule, timer persistence, heartbeat |
| `tests/features/concurrency.feature` | unit | Ignite race, lock expiry and reconciliation |
| `tests/features/watchdog.feature` | unit | Ceiling, missing heartbeat, drift, healthy no-op |
| `tests/features/adapter-valheim.feature` | contract, e2e | Valheim conformance and real-connection behaviour |

## Fakes

- **Fake adapter.** `tests/fake-adapter/adapter.sh` implements the [adapter interface](contracts/adapter-interface.md). Each subcommand reads its scripted result from an environment variable named `FAKE_<SUBCOMMAND>` (for example `FAKE_PLAYER_COUNT=unknown`, `FAKE_IS_READY=1`) and records each invocation to `$FAKE_LOG`. Unit tests of the agent point `BONFIRE_ADAPTER_DIR` at it.
- **Fake state row.** An in-memory dictionary with ETag semantics: a write with a stale ETag raises the same error type the real client does.
- **Fake Discord payloads.** Interactions built by a helper that signs them with a test Ed25519 key; the Function under test is configured with the matching public key.
- **Fake Azure client.** Records `start` and `deallocate` calls and returns a configurable power state.

## Runner

The runner is chosen in the Phase 1 spec together with the agent and Function languages. Feature files are runner-agnostic Gherkin; the only requirement on the runner is tag selection.

## Rules

1. Every scenario in a feature file has a step implementation before the phase that implements the behaviour is called done.
2. `@contract` scenarios run in CI on every change to `games/`.
3. `@e2e` scenarios run manually before a phase is closed, and their results are recorded in the phase spec.
