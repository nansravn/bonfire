# 0004. Watchdog: on-VM agent primary, Function safety net

**Status:** Accepted
**Date:** 2026-09-08

## Context

The VM must never stay allocated with zero players beyond the idle timeout, and must be extinguished even if the game or the whole VM hangs ([PRD](../prd.md) sections 3 and 6.4). Counting players needs the game's query protocol, which for Valheim is Steam A2S on UDP 2457. Querying it from outside the VM means opening the port to the internet and tolerating remote UDP flakiness.

## Decision

Two cooperating watchdogs:

- **The agent on the VM is primary.** A systemd timer runs every `idle_check_interval` minutes, asks the adapter for `player_count`, and drives the idle timer and warnings. After `idle_timeout_minutes` with zero players it stops the game cleanly and deallocates the VM through the VM's own managed identity.
- **The Function is the safety net.** A timer trigger every 15 minutes (the `WATCHDOG_INTERVAL_MINUTES` constant) deallocates the VM when it has been allocated longer than `max_session_hours` or the agent has not written a heartbeat for `heartbeat_stale_minutes`. It never reads the player count.

The state table is the contract between them: the agent writes a heartbeat and the last player count on every check; the Function acts only when the agent is silent or the ceiling is exceeded.

## Alternatives considered

### Function-only, polling A2S over the internet

Rejected. Requires opening the query port publicly and makes shutdown decisions on a lossy remote UDP query. A false zero would disconnect players.

### Agent-only

Rejected. A hung VM or a crashed agent would stay allocated indefinitely.

## Consequences

- Two code paths must be tested: the agent's idle logic and the Function's ceiling and heartbeat checks. Feature files `idle-shutdown.feature` and `watchdog.feature` cover them.
- The "unknown never extinguishes" rule applies to the agent only. The safety net's ceiling is absolute and can disconnect players, which is why it is announced one hour ahead; PRD section 11 counts any safety-net trigger as an agent bug to fix.
- The agent needs a managed identity with permission to deallocate its own VM, and the Function needs the same permission on that VM (Terraform `iam` module).
- The query port stays closed to the internet in v1; only the agent queries, on the loopback address.
